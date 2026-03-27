import subprocess

# How many times do you want the script to loop?
TOTAL_RUNS = 10 
LIMIT_PER_RUN = 500

for i in range(TOTAL_RUNS):
    print(f"\n=======================================")
    print(f"   Starting batch {i+1} of {TOTAL_RUNS}   ")
    print(f"=======================================\n")
    
    # This calls your specific Django command
    subprocess.run([
        "python", 
        "manage.py", 
        "import_movies", 
        "--limit", 
        str(LIMIT_PER_RUN)
    ])