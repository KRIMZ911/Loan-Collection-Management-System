"""
CMS Demo Launcher — double-click to run the Collection Management System.
"""

import sys
import os
import webbrowser
from threading import Timer

# Handle PyInstaller frozen paths
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
os.environ['FLASK_APP'] = 'app'


def main():
    print("=" * 60)
    print("  📊 CMS — Зээл Төлүүлэх Удирдлагын Систем")
    print("  Collection Management System — Demo")
    print("=" * 60)
    print()

    from app import create_app, db
    app = create_app()

    # Check if database needs seeding
    instance_dir = os.path.join(BASE_DIR, 'instance')
    db_path = os.path.join(instance_dir, 'collection.db')

    with app.app_context():
        if not os.path.exists(db_path) or os.path.getsize(db_path) < 1000:
            print("🌱 Анхны ажиллуулалт — өгөгдөл үүсгэж байна...")
            print("   (First run — generating demo data...)")
            print()
            db.create_all()
            from app.seed import seed
            seed()
            print()
            print("✅ Өгөгдөл амжилттай үүслээ!")
        else:
            print("✅ Өгөгдлийн сан бэлэн.")

    print()
    print("🌐 Сервер ажиллаж байна: http://localhost:5000")
    print("🌐 Server running at:    http://localhost:5000")
    print()
    print("❌ Зогсоохын тулд энэ цонхыг хаана уу.")
    print("❌ Close this window to stop the server.")
    print("=" * 60)

    # Open browser after short delay
    Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()

    # Run Flask server
    try:
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print()
        print("Server stopped.")


if __name__ == "__main__":
    main()
