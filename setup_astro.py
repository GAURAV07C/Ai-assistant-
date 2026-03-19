"""
A.D.A - ASTRO-STYLE SETUP
==========================
Install dependencies and configure ASTRO features
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required Python packages"""
    
    packages = [
        "langchain>=0.1.0",
        "langchain-core>=0.1.0", 
        "langchain-groq>=0.1.0",
        "langchain-huggingface>=0.0.1",
        "langchain-community>=0.0.1",
        "faiss-cpu>=1.7.0",
        "sentence-transformers>=2.2.0",
        "tavily>=0.2.0",
        "edge-tts>=6.1.0",
        "python-dotenv>=1.0.0",
    ]
    
    print("Installing dependencies...")
    for pkg in packages:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
            print(f"  ✓ {pkg}")
        except:
            print(f"  ✗ {pkg}")

def create_directories():
    """Create required directories"""
    dirs = [
        "database/learning_data",
        "database/chats_data", 
        "database/vector_store",
    ]
    
    print("\nCreating directories...")
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✓ {d}")

def main():
    print("=" * 50)
    print("A.D.A - ASTRO Features Setup")
    print("=" * 50)
    
    install_requirements()
    create_directories()
    
    print("\n" + "=" * 50)
    print("SETUP COMPLETE!")
    print("=" * 50)
    print("""
Next steps:
1. Copy backend/.env.example to backend/.env
2. Add your Groq API key (get free at https://console.groq.com)
3. Optional: Add Tavily API key for web search
4. Run: cd backend && python server.py
5. Open: http://localhost:5173
""")

if __name__ == "__main__":
    main()
