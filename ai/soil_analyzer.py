import google.generativeai as genai
import base64
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
    
    # Read and encode the image
    with open(image_path, "rb") as image_file:
        image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")
    
    media_type = get_image_media_type(image_path)
    
    # Create the analysis prompt
    prompt = """Analyze this soil image in detail and provide:

1. **Soil Type**: Identify the soil type (clay, sandy, silt, loam, etc.)
2. **Color**: Describe the soil color and what it indicates
3. **Texture**: Assess the texture and particle size
4. **Moisture Content**: Estimate the moisture level (dry, moist, wet)
5. **Organic Matter**: Estimate the presence of organic matter and decomposition
6. **Fertility Indicators**: What does this soil suggest about fertility?
7. **Potential Issues**: Any visible problems (erosion, compaction, contamination, etc.)?
8. **Recommendations**: Suggestions for soil improvement or use
9. **pH Estimation**: Based on appearance, estimate pH range
10. **Land Use Suitability**: What crops or uses would this soil be suitable for?

Please be thorough and technical in your analysis."""

    # Initialize the model
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Create image part for Gemini
    image_part = {
        "mime_type": media_type,
        "data": image_data,
    }
    
    print("Sending image to Gemini API for analysis...")
    print("Please wait...")
    print()
    
    # Send request to Gemini
    response = model.generate_content([prompt, image_part])
    
    return response.text

def interactive_mode():
    """Interactive mode for easy use in VS Code"""
    print("\n" + "="*60)
    print("SOIL IMAGE ANALYZER - Powered by Google Gemini")
    print("="*60 + "\n")
    
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
    print("-" * 60)
    print()
    
    try:
        analysis = analyze_soil(image_path, api_key)
        print(analysis)
        print("\n" + "-" * 60)
        print("Analysis complete!")
    except Exception as e:
        print(f"ERROR: {str(e)}")

def main():
    """Main function"""
    api_key = os.getenv('GEMINI_API_KEY')
    
    if len(sys.argv) < 2:
        # Interactive mode if no arguments
        interactive_mode()
    else:
        # Command line mode
        image_path = sys.argv[1]
        
        if not api_key:
            print("ERROR: GEMINI_API_KEY not found in .env file")
            sys.exit(1)
        
        if not Path(image_path).exists():
            print(f"ERROR: Image file '{image_path}' not found")
            sys.exit(1)
        
        print(f"Analyzing soil image: {image_path}")
        print("-" * 60)
        print()
        
        try:
            analysis = analyze_soil(image_path, api_key)
            print(analysis)
        except Exception as e:
            print(f"ERROR: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    main()