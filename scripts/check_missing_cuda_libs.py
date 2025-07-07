#!/usr/bin/env python3
"""
Verificar exatamente quais bibliotecas CUDA estão faltando
"""

import os
import subprocess
from pathlib import Path

def check_library(lib_name, paths_to_check):
    """Verificar se biblioteca existe em algum path"""
    found_paths = []
    
    for path in paths_to_check:
        lib_path = Path(path) / lib_name
        if lib_path.exists():
            found_paths.append(str(lib_path))
    
    return found_paths

def check_ldconfig(lib_name):
    """Verificar se biblioteca está disponível via ldconfig"""
    try:
        result = subprocess.run(['ldconfig', '-p'], capture_output=True, text=True)
        return lib_name in result.stdout
    except:
        return False

def main():
    """Verificar bibliotecas CUDA faltantes"""
    print("🔍 VERIFICANDO BIBLIOTECAS CUDA FALTANTES")
    print("=" * 50)
    
    # Bibliotecas que apareceram nos erros
    missing_libs = [
        "libcudnn.so.8",
        "libcublasLt.so.11", 
        "libcurand.so.10",
        "libcufft.so.10",
        "libcusolver.so.11",
        "libcusparse.so.11",
        "libcublas.so.11",
        "libnvrtc.so.11.8",
        "libcuinj64.so.11.8"
    ]
    
    # Paths onde procurar
    search_paths = [
        "/usr/local/cuda/lib64",
        "/usr/local/cuda-11.8/lib64", 
        "/usr/lib/x86_64-linux-gnu",
        "/home/pikachu/cuda/lib64",
        "/home/pikachu/miniconda3/envs/presence/lib",
        "/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/cublas/lib",
        "/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/curand/lib",
        "/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/cufft/lib",
        "/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/cusolver/lib",
        "/home/pikachu/miniconda3/envs/presence/lib/python3.10/site-packages/nvidia/cusparse/lib"
    ]
    
    print("📍 Paths de busca:")
    for path in search_paths:
        exists = "✅" if Path(path).exists() else "❌"
        print(f"  {exists} {path}")
    
    print(f"\n🔎 Verificando {len(missing_libs)} bibliotecas:")
    
    found_libs = {}
    missing_libs_final = []
    
    for lib in missing_libs:
        print(f"\n📚 {lib}:")
        
        # Verificar em paths específicos
        found_paths = check_library(lib, search_paths)
        
        # Verificar via ldconfig
        in_ldconfig = check_ldconfig(lib)
        
        if found_paths:
            print(f"  ✅ Encontrada em:")
            for path in found_paths:
                print(f"     {path}")
            found_libs[lib] = found_paths
        elif in_ldconfig:
            print(f"  ✅ Disponível via ldconfig")
            found_libs[lib] = ["system"]
        else:
            print(f"  ❌ NÃO ENCONTRADA")
            missing_libs_final.append(lib)
    
    print("\n" + "=" * 50)
    print("📊 RESUMO:")
    print(f"✅ Encontradas: {len(found_libs)}")
    print(f"❌ Faltando: {len(missing_libs_final)}")
    
    if missing_libs_final:
        print(f"\n🔴 BIBLIOTECAS FALTANDO:")
        for lib in missing_libs_final:
            print(f"  - {lib}")
        
        print(f"\n💡 COMO INSTALAR AS FALTANTES:")
        
        # Mapear bibliotecas para pacotes
        lib_to_package = {
            "libcudnn.so.8": "cuDNN 8.x (manual install)",
            "libcublasLt.so.11": "libcublas11 ou cuda-toolkit",
            "libcurand.so.10": "libcurand10",
            "libcufft.so.10": "libcufft10", 
            "libcusolver.so.11": "libcusolver11",
            "libcusparse.so.11": "libcusparse11",
            "libcublas.so.11": "libcublas11",
            "libnvrtc.so.11.8": "cuda-nvrtc-11-8",
            "libcuinj64.so.11.8": "cuda-cuinj64-11-8"
        }
        
        conda_libs = []
        apt_libs = []
        manual_libs = []
        
        for lib in missing_libs_final:
            package = lib_to_package.get(lib, "unknown")
            if "cuDNN" in package:
                manual_libs.append(f"  {lib} -> {package}")
            elif lib.startswith("libcu") and lib.endswith((".10", ".11")):
                apt_libs.append(f"  {package}")
            else:
                conda_libs.append(f"  {package}")
        
        if apt_libs:
            print(f"\n📦 Via APT:")
            print("sudo apt install -y \\")
            for pkg in apt_libs:
                print(f"  {pkg.strip()} \\")
        
        if conda_libs:
            print(f"\n🐍 Via Conda:")
            for pkg in conda_libs:
                print(f"conda install {pkg.strip()}")
        
        if manual_libs:
            print(f"\n🔧 Instalação Manual:")
            for item in manual_libs:
                print(item)
    else:
        print("\n🎉 TODAS AS BIBLIOTECAS ENCONTRADAS!")
        print("O sistema deve funcionar 100% com GPU!")

if __name__ == "__main__":
    main()