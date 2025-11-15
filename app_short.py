import subprocess
import os
from pathlib import Path
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import wave
import struct

# Configuration
EPUB_PATH = "./book.epub"
MODEL_NAME = "zipvoice"
CHECKPOINT = "iter-525000-avg-2.pt"
PROMPT_WAV = "prompt_short.wav"
PROMPT_TEXT = "ước gì bố tớ cũng được như"
LANG = "vi"
TOKENIZER = "espeak"
NUM_THREADS = 5
SPEED = 1.3
CHUNK_SIZE = 2500  # characters per chunk
OUTPUT_DIR = "./audio_chunks"
FINAL_OUTPUT = "./final_audiobook.wav"
PAUSE_BETWEEN_CHUNKS_MS = 1000
START_FROM_PERCENT = 24 

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

def extract_text_from_epub(epub_path, start_from_percent=0):
    """Extract all text content from EPUB file, optionally starting from a percentage"""
    book = epub.read_epub(epub_path)
    chapters = []
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            if text:
                chapters.append(text)
    
    full_text = ' '.join(chapters)
    
    # Calculate starting position based on percentage
    if start_from_percent > 0:
        start_pos = int(len(full_text) * (start_from_percent / 100))
        full_text = full_text[start_pos:]
        print(f"  → Starting from {start_from_percent}% ({start_pos:,} characters skipped)")
    
    return full_text

def chunk_text(text, chunk_size=500):
    """Split text into smaller chunks at sentence boundaries"""
    import re
    
    # Split text into sentences (handle common sentence endings)
    sentence_endings = r'[.!?]\s+'
    sentences = re.split(sentence_endings, text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_length = len(sentence)
        
        # If adding this sentence exceeds chunk_size, save current chunk
        if current_length > 0 and current_length + sentence_length > chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = []
            current_length = 0
        
        # Add sentence to current chunk
        current_chunk.append(sentence)
        current_length += sentence_length + 1
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks

def generate_audio_chunk(text, output_path, chunk_num):
    """Generate audio for a single text chunk"""
    cmd = [
        "python", "-m", "zipvoice.bin.infer_zipvoice",
        "--model-name", MODEL_NAME,
        "--checkpoint-name", CHECKPOINT,
        "--prompt-wav", PROMPT_WAV,
        "--prompt-text", PROMPT_TEXT,
        "--text", text,
        "--res-wav-path", output_path,
        "--lang", LANG,
        "--tokenizer", TOKENIZER,
        "--num-thread", str(NUM_THREADS),
        "--speed", str(SPEED)
    ]
    
    print(f"Processing chunk {chunk_num}...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✓ Chunk {chunk_num} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error processing chunk {chunk_num}: {e.stderr}")
        return False

def add_silence(duration_ms, sample_rate=22050, channels=1, sampwidth=2):
    """Generate silence frames for adding pauses"""
    num_frames = int(sample_rate * duration_ms / 1000)
    silence = b'\x00' * (num_frames * channels * sampwidth)
    return silence

def merge_wav_files(wav_files, output_path, pause_between_chunks_ms):
    """Merge multiple WAV files into one with pauses between chunks"""
    print(f"\nMerging {len(wav_files)} audio files with {pause_between_chunks_ms}ms pauses...")
    
    # Read the first file to get audio parameters
    with wave.open(wav_files[0], 'rb') as first_wav:
        params = first_wav.getparams()
        sample_rate = params.framerate
        channels = params.nchannels
        sampwidth = params.sampwidth
        
    # Create output file
    with wave.open(output_path, 'wb') as output_wav:
        output_wav.setparams(params)
        
        # Append all WAV files with pauses between them
        for i, wav_file in enumerate(wav_files):
            with wave.open(wav_file, 'rb') as input_wav:
                output_wav.writeframes(input_wav.readframes(input_wav.getnframes()))
            
            # Add pause after each chunk (except the last one)
            if i < len(wav_files) - 1:
                silence = add_silence(pause_between_chunks_ms, sample_rate, channels, sampwidth)
                output_wav.writeframes(silence)
            
            print(f"Merged {i+1}/{len(wav_files)}")
    
    print(f"✓ Final audiobook saved to: {output_path}")

def main():
    print("=" * 60)
    print("EPUB to Audio Converter using ZipVoice")
    print("=" * 60)
    
    # Step 1: Extract text from EPUB
    print(f"\n[1/4] Extracting text from {EPUB_PATH}...")
    full_text = extract_text_from_epub(EPUB_PATH, START_FROM_PERCENT)
    print(f"✓ Extracted {len(full_text)} characters")
    
    # Step 2: Split into chunks
    print(f"\n[2/4] Splitting text into chunks (max {CHUNK_SIZE} chars)...")
    chunks = chunk_text(full_text, CHUNK_SIZE)
    print(f"✓ Created {len(chunks)} chunks")
    
    # Step 3: Generate audio for each chunk
    print(f"\n[3/4] Generating audio chunks...")
    audio_files = []
    
    for i, chunk in enumerate(chunks, 1):
        output_file = os.path.join(OUTPUT_DIR, f"chunk_{i:04d}.wav")
        
        if generate_audio_chunk(chunk, output_file, i):
            audio_files.append(output_file)
        else:
            print(f"Warning: Skipping failed chunk {i}")
    
    print(f"\n✓ Generated {len(audio_files)} audio files")
    
    # Step 4: Merge all audio files
    if audio_files:
        print(f"\n[4/4] Merging audio files...")
        merge_wav_files(audio_files, FINAL_OUTPUT, PAUSE_BETWEEN_CHUNKS_MS)
        
        # Calculate total duration
        with wave.open(FINAL_OUTPUT, 'rb') as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration = frames / float(rate)
            print(f"\nFinal audiobook duration: {duration/60:.2f} minutes")
        
        print("\n" + "=" * 60)
        print("CONVERSION COMPLETE!")
        print("=" * 60)
    else:
        print("\n✗ No audio files were generated successfully")

if __name__ == "__main__":
    main()