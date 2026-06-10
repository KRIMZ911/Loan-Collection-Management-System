"""
Entry point for the Collection Management System.
Usage:
    python run.py          -> Run the server
    python run.py seed     -> Seed the database with sample data
"""
import sys
from app import create_app, db

app = create_app()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        with app.app_context():
            from app.seed import seed_database
            seed_database(db)
            print("\n✅ Database seeded successfully!")
    else:
        print("\n🚀 Collection Management System starting...")
        print("   Open http://127.0.0.1:5000 in your browser\n")
        app.run(host="0.0.0.0", port=5000, debug=app.config["DEBUG"])
