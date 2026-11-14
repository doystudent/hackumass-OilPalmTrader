import google.generativeai as genai
import sys
import os   
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def initialize_client(api_key):
    """Initialize the Gemini API client"""
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file")
    genai.configure(api_key=api_key)

def get_image_media_type(image_path):
    """Determine the media type based on file extension"""
    extension = Path(image_path).suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp"
    }
    return media_types.get(extension, "image/jpeg")

def analyze_soil(image_path, api_key):
    """Analyze soil from an image using Gemini API"""
    
    initialize_client(api_key)
    
    # Upload the image file
    image_file = genai.upload_file(image_path)
    
    # Comprehensive soil analysis prompt
    prompt = """Perform a detailed soil analysis based on visual indicators. Evaluate the soil systematically across these five key categories:

===== 1. COLOR AND MINERAL INDICATORS =====

Lightness/Value Analysis:
- Rate the overall surface darkness on a scale (Very Dark, Dark, Medium, Light, Very Light)
- Correlate with estimated Soil Organic Matter (SOM) content
- Assess surface moisture reflection

Hue and Chromaticity Analysis:
- Identify dominant color hues: Red, Yellow, Brown, Gray, Black
- Red/Reddish: Well-drained soils with oxidized iron
- Yellow/Golden: Moderately drained, older weathered soils
- Gray/Pale: Waterlogging, gleying, poor drainage
- Black: High organic matter content

===== 2. PHYSICAL TEXTURE AND PARTICLE DISTRIBUTION =====

Texture Classification:
- Sandy, Silty, Clayey, or Loamy
- Visible coarse grains for sandy
- Smooth, flour-like for silty
- Dense, fine-grained for clayey
- Balanced mixture for loamy

Surface Granularity and Roughness:
- Assess particle size: Fine, Medium, or Coarse
- Surface uniformity: Uniform, Stratified, or Mixed

===== 3. STRUCTURAL INTEGRITY AND AGGREGATION =====

Clodiness and Aggregate Assessment:
- Structure type: Granular, Blocky, Platy, Columnar, or Massive
- Aggregate size: Microaggregates, Small, Medium, or Large
- Structural quality: Strong, Moderate, or Weak

Cracking Patterns:
- Visible cracks: None, Few, Moderate, or Extensive
- Pattern: Polygonal, Linear, Random, or Dendritic
- Suggests expansive clays if extensive

Surface Crust:
- Porous and loose, Intermediate, or Sealed/Hard crust
- Crusting severity: None, Light, Moderate, or Heavy

===== 4. SURFACE INCLUSIONS AND DEBRIS =====

Gravel and Stoniness:
- Percentage coverage: <5%, 5-15%, 15-35%, or >35%
- Stone sizes and composition
- Drainage implications

Organic Residue:
- Organic matter coverage: <10%, 10-30%, 30-60%, or >60%
- Fresh litter, partially decomposed, or well-decomposed humus
- Litter layer thickness

===== 5. SURFACE MOISTURE STATE =====

Saturation Level:
- Dry: Light colored, matte, powdery
- Moist: Darker, rich color saturation
- Saturated/Wet: Darkest, glossy, specular highlights

===== FINAL ANALYSIS =====

Provide:
- Overall soil classification and health (1-10 scale)
- USDA texture classification
- Estimated Organic Matter: Low, Moderate, High, or Very High
- Estimated pH: Very Acidic, Acidic, Neutral, Alkaline, or Very Alkaline
- Drainage class
- Compaction status
- Key observations and concerns
- Management recommendations
- Suitable land uses"""

    print("Sending image to Gemini API for comprehensive soil analysis...")
    print("Analyzing: Color & Minerals | Texture | Structure | Inclusions | Moisture")
    print("Please wait...")
    print()
    
    try:
        # Use the vision model with uploaded file
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([prompt, image_file])
        
        # Delete the uploaded file
        genai.delete_file(image_file.name)
        
        return response.text
    except Exception as e:
        raise Exception(f"API Error: {str(e)}")

def interactive_mode():
    """Interactive mode for easy use in VS Code"""
    print("\n" + "="*70)
    print("COMPREHENSIVE SOIL IMAGE ANALYZER - Powered by Google Gemini")
    print("="*70)
    print("\nAnalyzing: Color & Minerals | Texture | Structure | Inclusions | Moisture")
    print("="*70 + "\n")
    
    # Check API key
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in .env file")
        print("Please add your API key to .env file")
        print("Get it from: https://aistudio.google.com/app/apikey")
        return
    
    # Ask for image path
    image_path = input("Enter the path to your soil image: ").strip()
    
    # Validate file exists
    if not Path(image_path).exists():
        print(f"\nERROR: Image file '{image_path}' not found")
        print(f"Current folder: {os.getcwd()}")
        return
    
    print(f"\nAnalyzing soil image: {image_path}")
    print("-" * 70)
    print()
    
    try:
        analysis = analyze_soil(image_path, api_key)
        print(analysis)
        print("\n" + "-" * 70)
        print("Analysis complete!")
    except Exception as e:
        print(f"ERROR: {str(e)}")

def main():
    """Main function"""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if len(sys.argv) < 2:
        interactive_mode()
    else:
        image_path = sys.argv[1]
        
        if not api_key:
            print("ERROR: GEMINI_API_KEY not found in .env file")
            sys.exit(1)
        
        if not Path(image_path).exists():
            print(f"ERROR: Image file '{image_path}' not found")
            sys.exit(1)
        
        print(f"Analyzing soil image: {image_path}")
        print("-" * 70)
        print()
        
        try:
            analysis = analyze_soil(image_path, api_key)
            print(analysis)
        except Exception as e:
            print(f"ERROR: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    main()
