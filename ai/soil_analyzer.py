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
    """Analyze soil from an image using Gemini API with comprehensive criteria"""
    
    initialize_client(api_key)
    
    # Read and encode the image
    with open(image_path, "rb") as image_file:
        image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")
    
    media_type = get_image_media_type(image_path)
    
    # Comprehensive soil analysis prompt
    prompt = """Perform a detailed soil analysis based on visual indicators. Evaluate the soil systematically across these five key categories:

===== 1. COLOR AND MINERAL INDICATORS =====

Lightness/Value Analysis:
- Rate the overall surface darkness on a scale (Very Dark, Dark, Medium, Light, Very Light)
- Correlate with estimated Soil Organic Matter (SOM) content: Darker soils typically indicate higher humus and carbon content
- Assess surface moisture reflection: Wet soil appears darker with less light reflection

Hue and Chromaticity Analysis:
- Identify dominant color hues: Red, Yellow, Brown, Gray, Black, or combinations
- Red/Reddish undertones: Indicate well-drained soils rich in oxidized iron (hematite/goethite), suggesting good aeration
- Yellow/Golden undertones: Indicate iron oxidation in moderately drained conditions, common in older weathered soils
- Gray/Pale tones: Possible indicators of waterlogging, gleying, poor drainage, or iron leaching
- Black tones: Often indicate high organic matter content or presence of minerals like magnetite

===== 2. PHYSICAL TEXTURE AND PARTICLE DISTRIBUTION =====

Texture Classification:
- Identify the dominant soil texture class: Sandy, Silty, Clayey, or Loamy
- Sandy soils: Visible coarse grains, grainy appearance, loose structure, particles easily distinguishable
- Silty soils: Smooth, flour-like appearance, fine uniform particles, minimal graininess
- Clayey soils: Dense, fine-grained matrix, plastic appearance, minimal individual particle visibility
- Loamy soils: Balanced mixture showing both coarse and fine particles, intermediate granularity

Surface Granularity and Roughness:
- Assess particle size distribution: Fine, Medium, or Coarse
- Evaluate surface uniformity: Uniform, Stratified, or Mixed particle sizes
- Estimate visual roughness scale: Very Smooth (silty/clay), Moderate (loamy), Coarse (sandy)
- Note any visible stratification or layering of different particle sizes

===== 3. STRUCTURAL INTEGRITY AND AGGREGATION =====

Clodiness and Aggregate Assessment:
- Identify soil peds (aggregates) structure type: Granular, Blocky, Platy, Columnar, or Massive
- Estimate aggregate size distribution: Microaggregates (<1mm), Small (1-5mm), Medium (5-25mm), or Large (>25mm)
- Assess aggregate stability: Well-defined stable aggregates indicate good soil health; weak or absent aggregates suggest poor structure
- Rate structural quality: Strong, Moderate, or Weak

Cracking Patterns and Shrink-Swell Behavior:
- Document visible surface cracks: None, Few, Moderate, or Extensive
- Describe crack pattern: Polygonal (indicating clay), Linear, Random, or Dendritic
- Estimate depth of visible cracks: Shallow surface cracks vs. deep fissures
- High density of cracks suggests expansive clays (smectite) with significant shrink-swell potential

Surface Crust and Compaction Indicators:
- Assess surface layer condition: Porous and loose, Intermediate, or Sealed/Hard crust
- Identify crusting severity: None, Light, Moderate, or Heavy surface sealing
- Evaluate surface integrity: Indicates compaction if very hard, possibly from heavy equipment or rain impact
- Rate porosity appearance: High (many visible pores), Moderate, or Low (dense, sealed surface)

===== 4. SURFACE INCLUSIONS AND DEBRIS =====

Gravel and Stoniness Fraction:
- Estimate percentage of surface area covered by gravel/stones: <5%, 5-15%, 15-35%, or >35%
- Categorize stone sizes: Small pebbles (<1cm), Medium gravel (1-5cm), Larger stones (>5cm)
- Assess stone composition: Quartz, limestone, basalt, or mixed rock types visible
- Rate drainage implications: Higher stoniness typically improves drainage but may reduce water retention

Organic Residue and Mulch Cover:
- Quantify visible organic matter coverage: <10%, 10-30%, 30-60%, or >60%
- Classify organic materials: Fresh plant litter, partially decomposed residue, well-decomposed humus, or crop stubble
- Assess decomposition stage: Fresh and recognizable plant parts, Partially decomposed, or Well-integrated humus
- Estimate litter layer thickness: Thin (<5mm), Moderate (5-15mm), or Thick (>15mm)

===== 5. SURFACE MOISTURE STATE =====

Saturation Level Classification:
- Dry condition: Light colored, matte appearance, powdery texture visible, no sheen or specular reflection
- Moist condition: Darker coloration, rich color saturation, visible color definition, slightly reduced reflectance
- Saturated/Wet condition: Darkest appearance, glossy or specular highlights, possible micro-puddling, color enhancement

Moisture Distribution:
- Assess moisture uniformity: Uniform moisture, Patchy/uneven distribution, or Localized wet zones
- Identify potential waterlogging areas: Any gleying indicators (gray spots), waterlogging features
- Rate drainage class implications: Excessively drained, Well-drained, Moderately well-drained, Imperfectly drained, or Poorly drained

===== SYNTHESIS AND RECOMMENDATIONS =====

Based on the comprehensive analysis above, provide:

Overall Soil Classification:
- Summarize the soil type and quality assessment
- Estimate USDA soil texture triangle classification
- Rate overall soil health on a scale of 1-10 with justification

Estimated Soil Properties:
- Estimated Organic Matter content: Low (<2%), Moderate (2-4%), High (4-6%), or Very High (>6%)
- Estimated pH range: Very Acidic (<5.5), Acidic (5.5-6.5), Neutral (6.5-7.5), Alkaline (7.5-8.5), or Very Alkaline (>8.5)
- Drainage classification: Excessively drained to Poorly drained
- Compaction status: None, Light, Moderate, or Severe

Key Observations:
- List the most significant visual indicators observed
- Highlight any concerns (compaction, erosion, waterlogging, etc.)
- Note any beneficial characteristics

Management Recommendations:
- Specific actions to improve soil structure and health
- Suggested amendments (organic matter, drainage improvement, etc.)
- Best-suited crops or land use based on current conditions
- Timeline for improvements if interventions are applied

Land Use Suitability:
- Rate suitability for: Crop production, Pasture, Forestry, Urban development, or Conservation
- Identify limiting factors for various uses"""

    # Initialize the model
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Create image part for Gemini
    image_part = {
        "mime_type": media_type,
        "data": image_data,
    }
    
    print("Sending image to Gemini API for comprehensive soil analysis...")
    print("Analyzing: Color & Minerals | Texture | Structure | Inclusions | Moisture")
    print("Please wait...")
    print()
    
    # Send request to Gemini
    response = model.generate_content([prompt, image_part])
    
    return response.text

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
