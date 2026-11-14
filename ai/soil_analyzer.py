import google.genai as genai
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def analyze_soil(image_path, api_key):
    """Analyze soil from an image using Gemini API"""
    
    client = genai.Client(api_key=api_key)
    
    prompt = """Analyze this soil image across 5 categories:

1. COLOR & MINERALS: Darkness, Hue, Oxidation levels

2. TEXTURE & PARTICLES: Sandy, Silty, Clayey, or Loamy

3. STRUCTURE & AGGREGATION: Clod types, cracks, crusting

4. INCLUSIONS: Gravel %, organic residue, mulch

5. MOISTURE: Dry, Moist, or Wet

Provide: soil type, health (1-10), organic matter %, pH, drainage, recommendations"""

    print("Analyzing soil image...")
    print("Please wait...")
    print()
    
    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        response = client.models.generate_content(
            model="models/gemini-3.5-flash",
            contents=[
                prompt,
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_data
                    }
                }
            ]
        )
        return response.text
    except Exception as e:
        raise Exception(f"API Error: {str(e)}")

def main():
    api_key = os.getenv('GEMINI_API_KEY')
    
    if not api_key:
        print("ERROR: GEMINI_API_KEY not in .env")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        image_path = input("Enter image path: ").strip()
    else:
        image_path = sys.argv[1]
    
    if not Path(image_path).exists():
        print(f"ERROR: Image not found: {image_path}")
        sys.exit(1)
    
    try:
        analysis = analyze_soil(image_path, api_key)
        print(analysis)
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    main()
