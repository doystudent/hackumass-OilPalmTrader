import google.genai as genai
from google.genai import types
import mimetypes
import sys
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class SoilReport(BaseModel):
    """What Gemini must return. The fixed choices are what the C++ trader matches on."""
    soil_type: str
    moisture: Literal["dry", "moist", "wet"]
    texture: Literal["sandy", "silty", "clayey", "loamy"]
    drainage: Literal["poor", "moderate", "good"]
    health: int                 # 1-10
    organic_matter_pct: float
    ph: float
    analysis: str               # the full written analysis
    recommendations: str


def analyze_soil(image_path, api_key):
    """Analyze soil from an image using Gemini API. Returns a SoilReport."""

    client = genai.Client(api_key=api_key)

    prompt = """Analyze this soil image across 5 categories:

1. COLOR & MINERALS: Darkness, Hue, Oxidation levels

2. TEXTURE & PARTICLES: Sandy, Silty, Clayey, or Loamy

3. STRUCTURE & AGGREGATION: Clod types, cracks, crusting

4. INCLUSIONS: Gravel %, organic residue, mulch

5. MOISTURE: Dry, Moist, or Wet

Provide: soil type, health (1-10), organic matter %, pH, drainage, recommendations.
Put the written category-by-category analysis in "analysis". For the other
fields give your single best estimate from the image."""

    print("Analyzing soil image...")
    print("Please wait...")
    print()

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"

        response = client.models.generate_content(
            model="models/gemini-3.5-flash",
            contents=[
                prompt,
                types.Part.from_bytes(data=image_data, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SoilReport,
            ),
        )
        return SoilReport.model_validate_json(response.text)
    except Exception as e:
        raise Exception(f"API Error: {str(e)}")


def print_report(report):
    print(report.analysis)
    print()
    print(f"Soil type:      {report.soil_type}")
    print(f"Moisture:       {report.moisture}")
    print(f"Texture:        {report.texture}")
    print(f"Drainage:       {report.drainage}")
    print(f"Health:         {report.health}/10")
    print(f"Organic matter: {report.organic_matter_pct}%")
    print(f"pH:             {report.ph}")
    print()
    print(f"Recommendations: {report.recommendations}")


def save_report(report, out_path):
    """Write the report as key=value lines for trading/trader --soil."""
    keys = ["moisture", "texture", "drainage", "health", "organic_matter_pct", "ph", "soil_type"]
    with open(out_path, "w") as f:
        for key in keys:
            value = str(getattr(report, key)).replace("\n", " ")
            f.write(f"{key}={value}\n")


def main():
    # Usage: soil_analyzer.py [image] [--out soil_report.txt]
    args = sys.argv[1:]
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        if i + 1 >= len(args):
            print("ERROR: --out needs a file path")
            sys.exit(1)
        out_path = args[i + 1]
        del args[i:i + 2]

    api_key = os.getenv('GEMINI_API_KEY')

    if not api_key:
        print("ERROR: GEMINI_API_KEY not in .env")
        sys.exit(1)

    if len(args) < 1:
        image_path = input("Enter image path: ").strip()
    else:
        image_path = args[0]

    if not Path(image_path).exists():
        print(f"ERROR: Image not found: {image_path}")
        sys.exit(1)

    try:
        report = analyze_soil(image_path, api_key)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

    print_report(report)
    if out_path:
        save_report(report, out_path)


if __name__ == "__main__":
    main()
