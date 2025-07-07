#!/usr/bin/env python3
"""
Custom Migration Runner for Camera Enhancement

This script handles custom database migrations for the enhanced camera model.
"""

import os
import sys
import importlib.util
from typing import List, Dict
from sqlalchemy import create_engine, text
from loguru import logger

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


class MigrationRunner:
    """Custom migration runner for database schema changes"""
    
    def __init__(self, database_url: str = None):
        self.database_url = database_url or settings.DATABASE_URL
        self.engine = create_engine(self.database_url)
        self.migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
        
    def get_available_migrations(self) -> List[Dict]:
        """Get list of available migration files"""
        migrations = []
        
        if not os.path.exists(self.migrations_dir):
            logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return migrations
            
        for filename in sorted(os.listdir(self.migrations_dir)):
            if filename.endswith('.py') and not filename.startswith('__'):
                migration_id = filename.replace('.py', '')
                migrations.append({
                    'id': migration_id,
                    'filename': filename,
                    'path': os.path.join(self.migrations_dir, filename)
                })
                
        return migrations
    
    def create_migration_table(self):
        """Create migration tracking table if it doesn't exist"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS applied_migrations (
                    migration_id VARCHAR PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
    
    def get_applied_migrations(self) -> List[str]:
        """Get list of already applied migrations"""
        self.create_migration_table()
        
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT migration_id FROM applied_migrations ORDER BY migration_id"))
            return [row[0] for row in result.fetchall()]
    
    def load_migration_module(self, migration_path: str):
        """Load migration module dynamically"""
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    def apply_migration(self, migration: Dict) -> bool:
        """Apply a single migration"""
        try:
            logger.info(f"Applying migration: {migration['id']}")
            
            # Load migration module
            migration_module = self.load_migration_module(migration['path'])
            
            # Check if migration has upgrade function
            if not hasattr(migration_module, 'upgrade'):
                logger.error(f"Migration {migration['id']} missing upgrade() function")
                return False
            
            # Create a mock alembic op object for our custom migrations
            class MockOp:
                def __init__(self, engine):
                    self.engine = engine
                    
                def execute(self, sql):
                    with self.engine.connect() as conn:
                        conn.execute(sql)
                        conn.commit()
            
            # Apply migration
            with self.engine.connect() as conn:
                # Create mock op object
                import sys
                sys.modules['op'] = MockOp(self.engine)
                
                # Execute upgrade
                migration_module.upgrade()
                
                # Mark migration as applied
                conn.execute(text(
                    "INSERT INTO applied_migrations (migration_id) VALUES (:migration_id)"
                ), {"migration_id": migration['id']})
                conn.commit()
                
            logger.info(f"Successfully applied migration: {migration['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply migration {migration['id']}: {e}")
            return False
    
    def rollback_migration(self, migration: Dict) -> bool:
        """Rollback a single migration"""
        try:
            logger.info(f"Rolling back migration: {migration['id']}")
            
            # Load migration module
            migration_module = self.load_migration_module(migration['path'])
            
            # Check if migration has downgrade function
            if not hasattr(migration_module, 'downgrade'):
                logger.error(f"Migration {migration['id']} missing downgrade() function")
                return False
            
            # Create mock op object
            class MockOp:
                def __init__(self, engine):
                    self.engine = engine
                    
                def execute(self, sql):
                    with self.engine.connect() as conn:
                        conn.execute(sql)
                        conn.commit()
            
            # Rollback migration
            with self.engine.connect() as conn:
                # Create mock op object
                import sys
                sys.modules['op'] = MockOp(self.engine)
                
                # Execute downgrade
                migration_module.downgrade()
                
                # Remove migration from applied list
                conn.execute(text(
                    "DELETE FROM applied_migrations WHERE migration_id = :migration_id"
                ), {"migration_id": migration['id']})
                conn.commit()
                
            logger.info(f"Successfully rolled back migration: {migration['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback migration {migration['id']}: {e}")
            return False
    
    def migrate_up(self) -> bool:
        """Apply all pending migrations"""
        logger.info("Starting database migration...")
        
        available_migrations = self.get_available_migrations()
        applied_migrations = self.get_applied_migrations()
        
        pending_migrations = [
            m for m in available_migrations 
            if m['id'] not in applied_migrations
        ]
        
        if not pending_migrations:
            logger.info("No pending migrations found")
            return True
        
        logger.info(f"Found {len(pending_migrations)} pending migrations")
        
        success = True
        for migration in pending_migrations:
            if not self.apply_migration(migration):
                success = False
                break
        
        if success:
            logger.info("All migrations applied successfully")
        else:
            logger.error("Migration failed")
            
        return success
    
    def migrate_down(self, target_migration: str = None) -> bool:
        """Rollback migrations to a target migration (or all if None)"""
        logger.info(f"Rolling back migrations to: {target_migration or 'beginning'}")
        
        available_migrations = self.get_available_migrations()
        applied_migrations = self.get_applied_migrations()
        
        # Find migrations to rollback (in reverse order)
        migrations_to_rollback = []
        for migration in reversed(available_migrations):
            if migration['id'] in applied_migrations:
                migrations_to_rollback.append(migration)
                if target_migration and migration['id'] == target_migration:
                    break
        
        if not migrations_to_rollback:
            logger.info("No migrations to rollback")
            return True
        
        logger.info(f"Rolling back {len(migrations_to_rollback)} migrations")
        
        success = True
        for migration in migrations_to_rollback:
            if not self.rollback_migration(migration):
                success = False
                break
        
        if success:
            logger.info("Rollback completed successfully")
        else:
            logger.error("Rollback failed")
            
        return success
    
    def status(self):
        """Show migration status"""
        available_migrations = self.get_available_migrations()
        applied_migrations = self.get_applied_migrations()
        
        logger.info("Migration Status:")
        logger.info("=" * 50)
        
        for migration in available_migrations:
            status = "APPLIED" if migration['id'] in applied_migrations else "PENDING"
            logger.info(f"{migration['id']:30} | {status}")
        
        logger.info("=" * 50)
        logger.info(f"Total: {len(available_migrations)} migrations")
        logger.info(f"Applied: {len(applied_migrations)} migrations")
        logger.info(f"Pending: {len(available_migrations) - len(applied_migrations)} migrations")


def main():
    """Main migration runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Migration Runner")
    parser.add_argument('command', choices=['up', 'down', 'status'], 
                       help='Migration command')
    parser.add_argument('--target', help='Target migration for rollback')
    
    args = parser.parse_args()
    
    runner = MigrationRunner()
    
    if args.command == 'up':
        success = runner.migrate_up()
        sys.exit(0 if success else 1)
    elif args.command == 'down':
        success = runner.migrate_down(args.target)
        sys.exit(0 if success else 1)
    elif args.command == 'status':
        runner.status()
        sys.exit(0)


if __name__ == "__main__":
    main()