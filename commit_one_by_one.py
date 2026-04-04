import subprocess
import sys
from tqdm import tqdm

def run_cmd(cmd):
    """Ejecuta un comando en la terminal y devuelve el código de salida y el output."""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr

def main():
    print("Obteniendo lista de archivos modificados y sin seguimiento (untracked)...")
    code, out, err = run_cmd("git status --porcelain")
    if code != 0:
        print("Error ejecutando 'git status':", err)
        sys.exit(1)
        
    lines = out.strip().split("\n")
    if not lines or lines == ['']:
        print("No hay cambios pendientes para hacer commit.")
        return
        
    files_to_commit = []
    for line in lines:
        if len(line) < 4:
            continue
        
        # El formato de 'git status --porcelain' es "XY PATH"
        # Status está en los primeros dos caracteres, el path a partir del índice 3.
        filepath = line[3:].strip()
        
        # Manejar archivos renombrados (ej: R  old_file -> new_file)
        if "->" in filepath:
            filepath = filepath.split("->")[1].strip()
            
        # Quitar comillas si la ruta contiene espacios o caracteres especiales
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = filepath[1:-1]
            
        files_to_commit.append(filepath)
        
    total_files = len(files_to_commit)
    print(f"Se encontraron {total_files} archivos para hacer commit.")
    print("Iniciando subida uno por uno...\n")
    
    # tqdm progress bar
    with tqdm(total=total_files, desc="Subiendo", unit="archivo") as pbar:
        for filepath in files_to_commit:
            # Update description to show current file (truncated if too long)
            desc_file = filepath if len(filepath) < 30 else "..." + filepath[-27:]
            pbar.set_description(f"Procesando: {desc_file}")
            
            # 1. Añadir archivo al staging area (git add)
            add_code, add_out, add_err = run_cmd(f'git add "{filepath}"')
            if add_code != 0:
                pbar.write(f"\n[Error] No se pudo añadir el archivo {filepath}. Saltando...\n{add_err}")
                pbar.update(1)
                continue
                
            # 2. Hacer commit
            commit_code, commit_out, commit_err = run_cmd('git commit -m "major: update scraping"')
            if commit_code != 0:
                # Silencioso si falla porque no hay cambios
                run_cmd(f'git reset HEAD "{filepath}"')
                pbar.update(1)
                continue
                
            # 3. Hacer push
            push_code, push_out, push_err = run_cmd('git push')
            if push_code != 0:
                pbar.write(f"\n[Error Crítico] Falló el push para {filepath}. Deteniendo el script para que revises:\n{push_err}")
                break
                
            pbar.update(1)
        
    print("\n¡Proceso finalizado!")

if __name__ == "__main__":
    main()
