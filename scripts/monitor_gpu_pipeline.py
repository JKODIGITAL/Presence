#!/usr/bin/env python3
"""
Monitor em tempo real do pipeline GPU
"""

import asyncio
import sys
import os
import time
import psutil
import GPUtil
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TextColumn

# Adicionar path do projeto
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

console = Console()


class GPUPipelineMonitor:
    """Monitor em tempo real do pipeline GPU"""
    
    def __init__(self):
        self.running = True
        self.stats = {
            'system': {},
            'gpu': {},
            'pipeline': {},
            'cameras': {},
            'nvenc': {},
            'recognition': {}
        }
        
    def get_system_stats(self):
        """Obter estatísticas do sistema"""
        self.stats['system'] = {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'memory_used_gb': psutil.virtual_memory().used / (1024**3),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3)
        }
        
    def get_gpu_stats(self):
        """Obter estatísticas da GPU"""
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]  # Primeira GPU
                self.stats['gpu'] = {
                    'name': gpu.name,
                    'load': gpu.load * 100,
                    'memory_used': gpu.memoryUsed,
                    'memory_total': gpu.memoryTotal,
                    'memory_percent': (gpu.memoryUsed / gpu.memoryTotal) * 100 if gpu.memoryTotal > 0 else 0,
                    'temperature': gpu.temperature
                }
            else:
                self.stats['gpu'] = {'error': 'Nenhuma GPU detectada'}
        except Exception as e:
            self.stats['gpu'] = {'error': str(e)}
    
    async def get_pipeline_stats(self):
        """Obter estatísticas do pipeline"""
        try:
            # Aqui você conectaria ao worker real via API ou socket
            # Por enquanto, vamos simular
            import random
            
            self.stats['pipeline'] = {
                'fps_input': random.randint(25, 30),
                'fps_output': random.randint(24, 29),
                'latency_ms': random.randint(10, 50),
                'queue_size': random.randint(0, 10)
            }
            
            self.stats['cameras'] = {
                'cam1': {
                    'status': 'online',
                    'frames_processed': random.randint(1000, 10000),
                    'fps': random.randint(25, 30)
                }
            }
            
            self.stats['nvenc'] = {
                'frames_encoded': random.randint(1000, 10000),
                'bitrate_mbps': random.uniform(1.5, 3.0),
                'encoding_time_ms': random.uniform(5, 15)
            }
            
            self.stats['recognition'] = {
                'faces_detected': random.randint(0, 5),
                'recognitions': random.randint(0, 3),
                'processing_time_ms': random.uniform(10, 30)
            }
            
        except Exception as e:
            self.stats['pipeline'] = {'error': str(e)}
    
    def create_system_panel(self) -> Panel:
        """Criar painel de sistema"""
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("CPU", f"{self.stats['system'].get('cpu_percent', 0):.1f}%")
        table.add_row("RAM", f"{self.stats['system'].get('memory_percent', 0):.1f}% "
                     f"({self.stats['system'].get('memory_used_gb', 0):.1f}/"
                     f"{self.stats['system'].get('memory_total_gb', 0):.1f} GB)")
        
        return Panel(table, title="💻 Sistema", border_style="blue")
    
    def create_gpu_panel(self) -> Panel:
        """Criar painel da GPU"""
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        gpu_stats = self.stats.get('gpu', {})
        
        if 'error' in gpu_stats:
            table.add_row("Status", f"[red]{gpu_stats['error']}[/red]")
        else:
            table.add_row("GPU", gpu_stats.get('name', 'N/A'))
            table.add_row("Load", f"{gpu_stats.get('load', 0):.1f}%")
            table.add_row("Memory", f"{gpu_stats.get('memory_percent', 0):.1f}% "
                         f"({gpu_stats.get('memory_used', 0):.0f}/"
                         f"{gpu_stats.get('memory_total', 0):.0f} MB)")
            table.add_row("Temp", f"{gpu_stats.get('temperature', 0)}°C")
        
        return Panel(table, title="🎮 GPU", border_style="green")
    
    def create_pipeline_panel(self) -> Panel:
        """Criar painel do pipeline"""
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        pipeline_stats = self.stats.get('pipeline', {})
        
        if 'error' in pipeline_stats:
            table.add_row("Status", f"[red]{pipeline_stats['error']}[/red]")
        else:
            table.add_row("FPS Input", f"{pipeline_stats.get('fps_input', 0)}")
            table.add_row("FPS Output", f"{pipeline_stats.get('fps_output', 0)}")
            table.add_row("Latency", f"{pipeline_stats.get('latency_ms', 0)} ms")
            table.add_row("Queue", f"{pipeline_stats.get('queue_size', 0)}")
        
        return Panel(table, title="📊 Pipeline", border_style="yellow")
    
    def create_nvenc_panel(self) -> Panel:
        """Criar painel do NVENC"""
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        nvenc_stats = self.stats.get('nvenc', {})
        
        table.add_row("Frames", f"{nvenc_stats.get('frames_encoded', 0):,}")
        table.add_row("Bitrate", f"{nvenc_stats.get('bitrate_mbps', 0):.2f} Mbps")
        table.add_row("Encode Time", f"{nvenc_stats.get('encoding_time_ms', 0):.1f} ms")
        
        return Panel(table, title="🎬 NVENC", border_style="magenta")
    
    def create_recognition_panel(self) -> Panel:
        """Criar painel de reconhecimento"""
        table = Table(show_header=False, box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        rec_stats = self.stats.get('recognition', {})
        
        table.add_row("Faces", f"{rec_stats.get('faces_detected', 0)}")
        table.add_row("Recognized", f"{rec_stats.get('recognitions', 0)}")
        table.add_row("Process Time", f"{rec_stats.get('processing_time_ms', 0):.1f} ms")
        
        return Panel(table, title="👤 Recognition", border_style="cyan")
    
    def create_layout(self) -> Layout:
        """Criar layout da interface"""
        layout = Layout()
        
        # Dividir em header e body
        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        # Header
        layout["header"].update(
            Panel(
                f"[bold blue]GPU Pipeline Monitor[/bold blue] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                box=None
            )
        )
        
        # Body - dividir em duas colunas
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Coluna esquerda
        layout["body"]["left"].split(
            self.create_system_panel(),
            self.create_gpu_panel(),
            self.create_pipeline_panel()
        )
        
        # Coluna direita
        layout["body"]["right"].split(
            self.create_nvenc_panel(),
            self.create_recognition_panel()
        )
        
        # Footer
        layout["footer"].update(
            Panel(
                "[dim]Pressione Ctrl+C para sair[/dim]",
                box=None
            )
        )
        
        return layout
    
    async def update_stats(self):
        """Atualizar todas as estatísticas"""
        while self.running:
            try:
                # Atualizar estatísticas
                self.get_system_stats()
                self.get_gpu_stats()
                await self.get_pipeline_stats()
                
                await asyncio.sleep(1)  # Atualizar a cada segundo
                
            except Exception as e:
                console.print(f"[red]Erro ao atualizar stats: {e}[/red]")
                await asyncio.sleep(1)
    
    async def run(self):
        """Executar monitor"""
        # Iniciar task de atualização
        update_task = asyncio.create_task(self.update_stats())
        
        try:
            with Live(self.create_layout(), refresh_per_second=2) as live:
                while self.running:
                    live.update(self.create_layout())
                    await asyncio.sleep(0.5)
                    
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitor encerrado pelo usuário[/yellow]")
        finally:
            self.running = False
            update_task.cancel()
            try:
                await update_task
            except asyncio.CancelledError:
                pass


async def main():
    """Função principal"""
    monitor = GPUPipelineMonitor()
    await monitor.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass