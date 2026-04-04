import os
import sys
from pathlib import Path
import re
from tqdm import tqdm

# Añadir el directorio raíz al path para poder importar helpers
sys.path.insert(0, str(Path(__file__).parent))

from scraping.utils.helpers import load_json_with_parts, save_json_with_parts

def main():
    data_dir = Path("data/json")
    if not data_dir.exists():
        print(f"No se encontró el directorio {data_dir}")
        return

    # Límite máximo para considerarlo gigante: 90 MB
    # Usaremos 85 MB como límite a la hora de guardar para estar súper seguros (GitHub límite = 100MB)
    THRESHOLD_BYTES = 90 * 1024 * 1024 

    bases_to_resave = set()
    large_files_info = []
    
    print("Escaneando archivos...")
    all_json_files = list(data_dir.glob("*.json"))
    
    # 1. Escanear todos los archivos JSON y encontrar los que superan el límite
    for filepath in tqdm(all_json_files, desc="Buscando archivos grandes"):
        # Ignorar archivos .bak y dejar que _OLD sean procesados SOLO si superan el tamaño ellos mismos.
        if ".bak" in filepath.name:
            continue
            
        size_bytes = filepath.stat().st_size
        if size_bytes >= THRESHOLD_BYTES:
            size_mb = size_bytes / (1024 * 1024)
            large_files_info.append((filepath.name, size_mb))
            
            # Obtener el base_name (sin _partX)
            stem = filepath.stem
            
            # Si el archivo es un backup (_OLD), lo tratamos como un archivo base en sí mismo
            # Así permitimos que se divida en _OLD_part1, _OLD_part2, etc.
            is_old = stem.endswith("_OLD")
            
            # Removemos "_partX" asegurando que mantenemos _OLD si lo tiene al final
            if "_part" in stem:
                if stem.endswith("_OLD") and "_part" in stem[:-4]:
                    # Ej: players_all_part1_OLD -> players_all_OLD
                    base_name = re.sub(r"_part\d+_OLD$", "_OLD", stem)
                else:
                    # Ej: players_all_part1 -> players_all
                    base_name = re.sub(r"_part\d+$", "", stem)
            else:
                base_name = stem
            
            bases_to_resave.add(base_name)

    if not bases_to_resave:
        print(f"\n¡Excelente! No se encontraron archivos mayores a {THRESHOLD_BYTES/(1024*1024):.0f}MB.")
        return

    print(f"\nSe encontraron {len(large_files_info)} archivo(s) que exceden el límite:")
    for fname, size in large_files_info:
        print(f" - {fname} ({size:.2f} MB)")
        
    print(f"\nEsto afecta a {len(bases_to_resave)} entidades base que serán re-guardadas.")
    print("Iniciando proceso de re-guardado (resave)...\n")
    
    with tqdm(total=len(bases_to_resave), desc="Procesando grupos") as pbar:
        for base_name in bases_to_resave:
            # Actualizar descripción truncada si es muy larga
            desc_name = base_name if len(base_name) < 20 else "..." + base_name[-17:]
            pbar.set_description(f"Procesando: {desc_name}")
            
            try:
                # 2. Cargar TODOS los datos de esa base a la memoria (une todas las partes automáticamente)
                data = load_json_with_parts(base_name)
                
                if not data:
                    pbar.write(f"\n[Error] No se pudieron cargar los datos o están vacíos para {base_name}.")
                    pbar.update(1)
                    continue
                    
                # 3. Antes de guardar, eliminar manualmente TODOS los archivos asociados a esta base
                # (El single json y cualquier _partX.json viejo, para asegurar que no queden restos)
                deleted_count = 0
                # Intentar borrar base_name.json
                base_file = data_dir / f"{base_name}.json"
                if base_file.exists():
                    base_file.unlink()
                    deleted_count += 1
                    
                # Intentar borrar las partes base_name_partX.json
                for part_file in data_dir.glob(f"{base_name}_part*.json"):
                    if ".bak" in part_file.name:
                        continue
                    
                    # Si el base_name NO es _OLD, no borramos los _OLD que compartan prefijo.
                    # Por ejemplo, si base_name es "players_all_2022", no queremos borrar "players_all_2022_part1_OLD.json".
                    # Si base_name es "players_all_2022_OLD", ENTONCES sí queremos borrarlos (porque ese es el archivo que estamos re-procesando).
                    is_base_old = base_name.endswith("_OLD")
                    is_part_old = part_file.stem.endswith("_OLD")
                    
                    if not is_base_old and is_part_old:
                        continue
                        
                    try:
                        part_file.unlink()
                        deleted_count += 1
                    except OSError as e:
                        pbar.write(f"\n[Aviso] No se pudo eliminar {part_file.name}: {e}")
                        
                # 4. Volver a guardar con el límite estricto de 90MB
                success = save_json_with_parts(data, base_name)
                
                if not success:
                    pbar.write(f"\n[Error] Hubo un problema al re-guardar {base_name}.")
                    
            except Exception as e:
                pbar.write(f"\n[Error Inesperado en {base_name}]: {e}")
                
            pbar.update(1)

    print("\nProceso de re-guardado finalizado.")
    print("Ejecuta tu script de commits para subir los nuevos archivos divididos.")

if __name__ == "__main__":
    main()
