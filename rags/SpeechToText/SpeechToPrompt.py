import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import time
from datetime import datetime
from transformers import pipeline
import torch
import sys
import glob # For finding files for deletion

# Platform-specific imports for non-blocking keyboard input
if os.name == 'nt':  # Windows
    import msvcrt
else:  # POSIX (Linux, macOS)
    import select

# --- Configuration ---
SAMPLE_RATE = 16000
CHANNELS = 1
OUTPUT_FOLDER = "recordings" # All recordings go here and will be deleted from here
MODEL_NAME = "openai/whisper-base" # tiny, base, small, medium, large, large-v2, large-v3
BLOCK_DURATION = 0.5 # Duration of each audio chunk in seconds

def ensure_output_folder():
    """Creates the output folder if it doesn't exist."""
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"Created folder: {OUTPUT_FOLDER}")

def delete_all_recordings(folder_path=OUTPUT_FOLDER, file_extension=".wav"):
    """
    Deletes all files with the specified extension from the given folder.
    """
    if not os.path.isdir(folder_path):
        print(f"Info: Folder '{folder_path}' does not exist. Nothing to delete.")
        return

    # Create a pattern to match files, e.g., "recordings/*.wav"
    file_pattern_to_delete = os.path.join(folder_path, f"*{file_extension}")
    files_to_delete = glob.glob(file_pattern_to_delete)

    if not files_to_delete:
        print(f"Info: No '{file_extension}' files found in '{folder_path}' to delete.")
        return

    print(f"\nAttempting to delete {len(files_to_delete)} '{file_extension}' file(s) from '{folder_path}':")
    deleted_count = 0
    failed_count = 0
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
            print(f"  Deleted: {file_path}")
            deleted_count += 1
        except OSError as e:
            print(f"  Error deleting {file_path}: {e}")
            failed_count += 1

    if failed_count == 0 and deleted_count > 0:
        print("Successfully deleted all targeted recordings.")
    elif deleted_count > 0:
        print(f"Successfully deleted {deleted_count} recordings, but {failed_count} deletions failed.")
    elif failed_count > 0 :
        print(f"Failed to delete {failed_count} recordings.")
    # No message if nothing was there to delete initially or if folder didn't exist.

def record_audio_until_keypress(filename):
    """Records audio from the microphone until Enter is pressed, then saves it."""
    print("\n--- Starting Recording ---")
    print("Press ENTER to stop recording.")
    print("Speak now!")

    recorded_frames = []

    def audio_callback(indata, frames, time_info, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, file=sys.stderr)
        recorded_frames.append(indata.copy())

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                             dtype='float32', callback=audio_callback,
                             blocksize=int(SAMPLE_RATE * BLOCK_DURATION)):
            while True:
                input()
                break
    except Exception as e:
        print(f"Error during recording: {e}")
        return None
    except KeyboardInterrupt:
        print("\nRecording interrupted by user (Ctrl+C).")
        if not recorded_frames: # If interrupted before any audio, return None
            return None
        # If interrupted after some audio, still try to process it

    print("Recording stopped.")

    if not recorded_frames:
        print("No audio recorded.")
        return None

    recording = np.concatenate(recorded_frames, axis=0)
    sf.write(filename, recording, SAMPLE_RATE)
    print(f"Recording saved to {filename}")
    return filename

def transcribe_audio(audio_path, device, torch_dtype):
    """Transcribes the given audio file using Hugging Face pipeline."""
    print(f"\nLoading transcription model: {MODEL_NAME} (this might take a moment on first run)...")
    try:
        transcriber = pipeline(
            "automatic-speech-recognition",
            model=MODEL_NAME,
            device=device,
            torch_dtype=torch_dtype,
            generate_kwargs={"return_timestamps": True} # Handles long audio
        )
        print("Model loaded. Starting transcription...")
        result = transcriber(audio_path)
        # print(f"DEBUG: Full transcription result: {result}") # Uncomment to see raw output

        transcription_text = ""
        if isinstance(result, dict) and "text" in result:
            transcription_text = result["text"]
        elif isinstance(result, dict) and "chunks" in result and isinstance(result["chunks"], list):
            transcription_text = " ".join([chunk["text"].strip() for chunk in result["chunks"]])
        elif isinstance(result, str):
             transcription_text = result
        else:
            print(f"Warning: Unexpected transcription result structure: {type(result)}")
            transcription_text = str(result)

        print("\n--- Transcription ---")
        print(transcription_text.strip())
        print("---------------------")
        return transcription_text.strip()
    except Exception as e:
        print(f"Error during transcription: {e}")
        print("Make sure 'ffmpeg' is installed and in your system's PATH.")
        return None

def main():
    ensure_output_folder() # Make sure output folder exists

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # The filename now uses the global OUTPUT_FOLDER
    filename = os.path.join(OUTPUT_FOLDER, f"recording_{timestamp}.wav")

    recorded_file = record_audio_until_keypress(filename)

    # Determine device for Hugging Face
    if torch.cuda.is_available():
        device = "cuda:0"
        torch_dtype = torch.float16
        print(f"\nUsing GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = "cpu"
        torch_dtype = torch.float32
        print("\nUsing CPU. Transcription might be slower.")

    if recorded_file:
        transcription_result = transcribe_audio(recorded_file, device, torch_dtype)
        # Deletion happens after attempt to transcribe, regardless of success
        # as long as a file was recorded.
    else:
        print("No audio file was recorded or saved, skipping transcription.")

    # Clean up all recordings in the folder after this session's processing
    print("\n--- Cleaning up recordings in the folder ---")
    delete_all_recordings(folder_path=OUTPUT_FOLDER, file_extension=".wav")

    print("\nSession finished.")


if __name__ == "__main__":
    # Check if a microphone is available
    try:
        print("Available audio devices:")
        print(sd.query_devices())
        default_input_device_index = sd.default.device[0]
        if default_input_device_index == -1:
             print("\nWARNING: No default input microphone found by sounddevice.")
             print("Please ensure a microphone is connected and configured in your OS.")
        else:
            print(f"Using default input device: {sd.query_devices(default_input_device_index)['name']}")
    except Exception as e:
        print(f"Could not query audio devices: {e}")
        print("Ensure you have a microphone connected and sounddevice is working correctly.")
        exit()

    print("This script records audio until you press ENTER.")
    print("Ensure this terminal window is active to capture the ENTER key press.")
    main()