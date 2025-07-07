#!/usr/bin/env python3
"""
Script para diagnosticar problemas no sistema de reconhecimento facial
"""

import sys
import os
import asyncio
import time

# Adicionar o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.database import get_db_sync
from app.database import models
from app.core.recognition_engine import RecognitionEngine
from loguru import logger

async def diagnose_recognition_system():
    """Diagnosticar sistema de reconhecimento facial"""
    
    logger.info("🔍 Iniciando diagnóstico do sistema de reconhecimento facial...")
    
    try:
        # 1. Verificar banco de dados
        logger.info("📊 Verificando banco de dados...")
        db_gen = get_db_sync()
        db = next(db_gen)
        
        # Contar pessoas por status
        total_people = db.query(models.Person).filter(models.Person.is_unknown == False).count()
        active_people = db.query(models.Person).filter(
            models.Person.status == "active",
            models.Person.is_unknown == False
        ).count()
        pending_people = db.query(models.Person).filter(
            models.Person.status == "pending",
            models.Person.is_unknown == False
        ).count()
        inactive_people = db.query(models.Person).filter(
            models.Person.status == "inactive",
            models.Person.is_unknown == False
        ).count()
        
        # Contar pessoas com embeddings
        people_with_embeddings = db.query(models.Person).filter(
            models.Person.face_encoding.isnot(None),
            models.Person.is_unknown == False
        ).count()
        
        # Contar pessoas com detecção habilitada (se campo existir)
        try:
            detection_enabled_count = db.query(models.Person).filter(
                models.Person.detection_enabled == True,
                models.Person.is_unknown == False
            ).count()
        except:
            detection_enabled_count = "Campo detection_enabled não existe ainda"
        
        logger.info("📊 Estatísticas do banco de dados:")
        logger.info(f"  • Total de pessoas: {total_people}")
        logger.info(f"  • Pessoas ativas: {active_people}")
        logger.info(f"  • Pessoas pendentes: {pending_people}")
        logger.info(f"  • Pessoas inativas: {inactive_people}")
        logger.info(f"  • Pessoas com embeddings: {people_with_embeddings}")
        logger.info(f"  • Pessoas com detecção habilitada: {detection_enabled_count}")
        
        # 2. Verificar Recognition Engine
        logger.info("🧠 Verificando Recognition Engine...")
        try:
            engine = RecognitionEngine()
            
            if engine.is_initialized:
                logger.info("✅ Recognition Engine inicializado com sucesso")
                
                # Carregar faces conhecidas
                await engine.load_known_faces()
                
                logger.info(f"  • Faces carregadas no engine: {len(engine.face_embeddings)}")
                logger.info(f"  • FAISS disponível: {engine.use_faiss}")
                
                if engine.use_faiss and engine.faiss_index:
                    logger.info(f"  • Faces no índice FAISS: {engine.faiss_index.ntotal}")
                
            else:
                logger.warning("⚠️ Recognition Engine não foi inicializado")
                logger.info("  • Verifique se o GPU está disponível")
                logger.info("  • Verifique se as dependências estão instaladas")
                
        except Exception as e:
            logger.error(f"❌ Erro no Recognition Engine: {e}")
        
        # 3. Verificar pessoas pendentes há muito tempo
        logger.info("⏳ Verificando pessoas pendentes...")
        from datetime import datetime, timedelta
        
        five_minutes_ago = datetime.now() - timedelta(minutes=5)
        old_pending = db.query(models.Person).filter(
            models.Person.status == "pending",
            models.Person.updated_at < five_minutes_ago,
            models.Person.is_unknown == False
        ).all()
        
        if old_pending:
            logger.warning(f"⚠️ Encontradas {len(old_pending)} pessoas pendentes há mais de 5 minutos:")
            for person in old_pending[:5]:  # Mostrar apenas os primeiros 5
                logger.warning(f"  • {person.name} (ID: {person.id}) - Pendente desde: {person.updated_at}")
            
            if len(old_pending) > 5:
                logger.warning(f"  • ... e mais {len(old_pending) - 5} pessoas")
                
            logger.info("💡 Sugestão: Execute o endpoint /api/v1/people/reprocess-pending")
        else:
            logger.info("✅ Nenhuma pessoa pendente há muito tempo")
        
        # 4. Verificar logs de reconhecimento recentes
        logger.info("📝 Verificando logs de reconhecimento...")
        recent_logs = db.query(models.RecognitionLog).filter(
            models.RecognitionLog.timestamp >= datetime.now() - timedelta(hours=1)
        ).count()
        
        logger.info(f"  • Reconhecimentos na última hora: {recent_logs}")
        
        if recent_logs == 0:
            logger.warning("⚠️ Nenhum reconhecimento detectado na última hora")
            logger.info("💡 Possíveis causas:")
            logger.info("  • Camera Worker não está rodando")
            logger.info("  • Recognition Worker não está rodando")
            logger.info("  • Nenhuma pessoa ativa com embeddings")
            logger.info("  • Câmeras não estão ativas")
        
        # 5. Verificar arquivos de imagem
        logger.info("🖼️ Verificando arquivos de imagem...")
        people_with_images = db.query(models.Person).filter(
            models.Person.thumbnail_path.isnot(None),
            models.Person.is_unknown == False
        ).all()
        
        missing_images = 0
        for person in people_with_images:
            if not os.path.exists(person.thumbnail_path):
                missing_images += 1
        
        logger.info(f"  • Pessoas com caminho de imagem: {len(people_with_images)}")
        logger.info(f"  • Imagens ausentes no sistema de arquivos: {missing_images}")
        
        if missing_images > 0:
            logger.warning(f"⚠️ {missing_images} pessoas têm caminho de imagem mas o arquivo não existe")
        
        # 6. Resumo e recomendações
        logger.info("📋 Resumo do diagnóstico:")
        
        if pending_people > 0:
            logger.warning(f"⚠️ {pending_people} pessoas estão pendentes - considere reprocessar")
        
        if people_with_embeddings < active_people:
            logger.warning(f"⚠️ Nem todas as pessoas ativas têm embeddings ({people_with_embeddings}/{active_people})")
        
        if recent_logs == 0:
            logger.warning("⚠️ Sistema de reconhecimento pode não estar funcionando")
        
        if missing_images > 0:
            logger.warning(f"⚠️ {missing_images} imagens ausentes - considere reprocessar ou remover pessoas")
        
        logger.info("✅ Diagnóstico concluído!")
        
    except Exception as e:
        logger.error(f"❌ Erro durante o diagnóstico: {e}")
    
    finally:
        try:
            db.close()
        except:
            pass

def main():
    """Executar diagnóstico"""
    asyncio.run(diagnose_recognition_system())

if __name__ == "__main__":
    main()