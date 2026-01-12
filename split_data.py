import json
import os
import math

def split_geojson(input_file, output_dir, max_size_mb=24):
    """
    Splits a GeoJSON file into smaller chunks based on a target size in MB.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Loading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    features = data.get('features', [])
    total_features = len(features)
    print(f"Total features found: {total_features}")

    # Estimate size per feature to calculate chunks
    file_size_mb = os.path.getsize(input_file) / (1024 * 1024)
    print(f"File size: {file_size_mb:.2f} MB")
    
    # Aggressively split to ensure < 25MB. 
    # Previous attempt with 5 chunks resulted in one 63MB chunk due to uneven feature sizes.
    # Let's target 5MB per chunk average to be safe, which gives plenty of buffer.
    target_chunk_mb = 5
    num_chunks = math.ceil(file_size_mb / target_chunk_mb) 
    
    # Ensure at least 4 chunks as per prompt, but likely will be ~20
    num_chunks = max(num_chunks, 4) 
    
    chunk_size = math.ceil(total_features / num_chunks)
    print(f"Splitting into {num_chunks} chunks (approx {chunk_size} features each)...")

    for i in range(num_chunks):
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, total_features)
        
        chunk_features = features[start_idx:end_idx]
        
        chunk_data = {
            "type": "FeatureCollection",
            "features": chunk_features,
            # Preserve crs if present, though often standard GeoJSON is 4326 by default
            "crs": data.get("crs") 
        }
        
        output_filename = os.path.join(output_dir, f"sitios_propuestos_part{i+1}.geojson")
        with open(output_filename, 'w', encoding='utf-8') as outfile:
            json.dump(chunk_data, outfile)
        
        print(f"Saved {output_filename} ({len(chunk_features)} features)")

    print("Splitting complete.")

if __name__ == "__main__":
    # Adjust paths based on the project structure
    # Script is in root, data is in ./data
    INPUT_FILE = os.path.join("data", "sitios_prior_propuestos.json") 
    OUTPUT_DIR = os.path.join("data", "chunks")
    
    if os.path.exists(INPUT_FILE):
        split_geojson(INPUT_FILE, OUTPUT_DIR)
    else:
        print(f"Error: Input file {INPUT_FILE} not found.")
