import subprocess
import sys
import shutil

def run_cmd(cmd):
    """Ejecuta un comando en la terminal y devuelve el código de salida y el output."""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr

def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='█', print_end="\r"):
    """
    Llama a esta función en un bucle para crear una barra de progreso en la terminal.
    """
    # Truncate suffix if it's too long for the terminal
    term_width = shutil.get_terminal_size((100, 20)).columns
    
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    
    # Calculate how much space we have for the suffix
    base_string = f'{prefix} |{bar}| {percent}% '
    max_suffix_len = term_width - len(base_string) - 2
    
    if len(suffix) > max_suffix_len and max_suffix_len > 3:
        suffix = "..." + suffix[-(max_suffix_len-3):]
    
    # Pad suffix with spaces to clear any previous longer text
    padded_suffix = suffix.ljust(max_suffix_len) if max_suffix_len > 0 else suffix
        
    print(f'\r{base_string}{padded_suffix}', end=print_end)
    
    if iteration == total: 
        print()

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
    
    # Mostrar la barra inicial en 0%
    print_progress_bar(0, total_files, prefix='Progreso:', suffix='Iniciando...', length=40)
    
    for i, filepath in enumerate(files_to_commit, 1):
        # Actualizar la barra con el archivo actual
        print_progress_bar(i-1, total_files, prefix='Progreso:', suffix=f'Subiendo: {filepath}', length=40)
        
        # 1. Añadir archivo al staging area (git add)
        add_code, add_out, add_err = run_cmd(f'git add "{filepath}"')
        if add_code != 0:
            print(f"\n[Error] No se pudo añadir el archivo {filepath}. Saltando...\n{add_err}")
            continue
            
        # 2. Hacer commit
        commit_code, commit_out, commit_err = run_cmd('git commit -m "major: update scraping"')
        if commit_code != 0:
            # Silencioso si falla porque no hay cambios
            run_cmd(f'git reset HEAD "{filepath}"')
            continue
            
        # 3. Hacer push
        push_code, push_out, push_err = run_cmd('git push')
        if push_code != 0:
            print(f"\n[Error Crítico] Falló el push para {filepath}. Deteniendo el script para que revises:\n{push_err}")
            break
            
        # Actualizar la barra al terminar este archivo
        print_progress_bar(i, total_files, prefix='Progreso:', suffix=f'Completado: {filepath}', length=40)
        
    print("\n¡Proceso finalizado!")

if __name__ == "__main__":
    main()
