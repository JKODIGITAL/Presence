#!/usr/bin/env python3
"""
Database Migration Script for Enhanced Camera Model

This script applies the database migrations for the enhanced camera model
with performance metrics and validation capabilities.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.db.migrate import MigrationRunner
from loguru import logger


def main():
    """Run database migration for enhanced camera model"""
    logger.info("Starting database migration for enhanced camera model")
    
    try:
        # Create migration runner
        runner = MigrationRunner()
        
        # Show current status
        logger.info("Current migration status:")
        runner.status()
        
        # Apply pending migrations
        logger.info("\nApplying pending migrations...")
        success = runner.migrate_up()
        
        if success:
            logger.info("✅ Database migration completed successfully!")
            logger.info("\nEnhanced camera model features now available:")
            logger.info("- Performance metrics tracking (latency, FPS, quality)")
            logger.info("- Authentication credentials storage")
            logger.info("- Camera capabilities detection")
            logger.info("- Connection test results logging")
            logger.info("- Related performance and capability tables")
        else:
            logger.error("❌ Database migration failed!")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Migration error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()