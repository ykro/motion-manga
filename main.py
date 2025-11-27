import os
import time
import json
import typer
from typing import List, Optional, Callable, Any
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from google import genai
from google.genai import types
import imageio_ffmpeg
import subprocess

# Load environment variables
load_dotenv()

# Initialize Typer app and Rich console
app = typer.Typer()
console = Console()

# Initialize Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    console.print("[bold red]Error:[/bold red] GOOGLE_API_KEY not found in .env file.")
    raise typer.Exit(code=1)

client = genai.Client(api_key=api_key)

OUTPUT_DIR = Path("output")

def retry_api_call(max_retries: int = 3, delay: int = 5):
    """Decorator to retry API calls on exceptions."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        raise e
                    console.print(f"[yellow]API call failed ({e}). Retrying in {delay}s... ({retries}/{max_retries})[/yellow]")
                    time.sleep(delay)
        return wrapper
    return decorator

def optimize_video(video_path: Path) -> Path:
    """
    Optimizes video if larger than 10MB by resizing height to 720px.
    Returns the path to the optimized video (or original if no optimization needed).
    """
    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    
    if file_size_mb <= 10:
        return video_path

    console.print(f"[yellow]Optimizing {video_path.name} ({file_size_mb:.2f} MB)...[/yellow]")
    
    output_path = OUTPUT_DIR / f"optimized_{video_path.name}"
    
    # Construct ffmpeg command to resize height to 720px, maintaining aspect ratio
    # -vf scale=-2:720 ensures width is divisible by 2 (required by some encoders) and height is 720
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y", # Overwrite output file
        "-i", str(video_path),
        "-vf", "scale=-2:720",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        str(output_path)
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"[green]Optimized {video_path.name} -> {output_path.name}[/green]")
        return output_path
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error optimizing video {video_path.name}: {e}[/bold red]")
        return video_path # Fallback to original if optimization fails

def remove_audio(video_path: Path) -> Path:
    """
    Creates a copy of the video without audio.
    Returns the path to the no-audio video.
    """
    output_path = OUTPUT_DIR / f"{video_path.stem}_noaudio{video_path.suffix}"
    
    console.print(f"[yellow]Removing audio from {video_path.name}...[/yellow]")
    
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", str(video_path),
        "-c:v", "copy",
        "-an", # Remove audio
        str(output_path)
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"[green]Created no-audio version: {output_path.name}[/green]")
        return output_path
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error removing audio from {video_path.name}: {e}[/bold red]")
        return video_path # Fallback

@retry_api_call(max_retries=3, delay=5)
def generate_content_with_retry(model, contents, config=None):
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

def upload_file(path: Path):
    """Uploads a file to Gemini API and waits for it to be active."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Uploading {path.name}...", total=None)
        
        # Upload file
        file_obj = client.files.upload(file=path)
        
        # Wait for processing
        while file_obj.state.name == "PROCESSING":
            progress.update(task, description=f"Processing {path.name}...")
            time.sleep(2)
            file_obj = client.files.get(name=file_obj.name)
            
        if file_obj.state.name != "ACTIVE":
            raise Exception(f"File {file_obj.name} failed to process. State: {file_obj.state.name}")
            
        progress.update(task, description=f"Ready: {path.name}")
        return file_obj

@app.command()
def main(
    videos: List[Path] = typer.Argument(..., help="Paths to video files (max 3)", exists=True, file_okay=True, dir_okay=False, readable=True)
):
    """
    MotionManga: Convert videos into a manga story with images.
    """
    if len(videos) > 3:
        console.print("[bold red]Error:[/bold red] You can provide at most 3 video files.")
        raise typer.Exit(code=1)

    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)

    console.print(Panel.fit("[bold magenta]MotionManga Generator[/bold magenta]"))

    # 1. Optimize Videos (for Story - keeps audio)
    optimized_videos = []
    for video in videos:
        optimized_videos.append(optimize_video(video))

    # 2. Prepare No-Audio Videos (for Images)
    no_audio_videos = []
    for video in optimized_videos:
        no_audio_videos.append(remove_audio(video))

    # 3. Upload Videos
    uploaded_files_story = []
    uploaded_files_images = []
    
    try:
        # Upload story videos (with audio)
        console.print("[cyan]Uploading videos for Story Generation...[/cyan]")
        for video in optimized_videos:
            uploaded_files_story.append(upload_file(video))
            
        # Upload image videos (no audio)
        console.print("[cyan]Uploading videos for Image Generation...[/cyan]")
        for video in no_audio_videos:
            uploaded_files_images.append(upload_file(video))
            
    except Exception as e:
        console.print(f"[bold red]Error uploading files: {e}[/bold red]")
        raise typer.Exit(code=1)

    # 4. Generate Story
    console.print("[bold cyan]Generating Story...[/bold cyan]")
    try:
        with open("story.md", "r") as f:
            story_prompt = f.read()
            
        response = generate_content_with_retry(
            model="gemini-3-pro-preview",
            contents=[story_prompt] + uploaded_files_story,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        story_json = json.loads(response.text)
        
        # Extract pages and character concept
        # Handle both old (flat dict) and new (nested with character_concept) structures for backward compatibility
        if "pages" in story_json:
            pages = story_json["pages"]
            character_concept = story_json.get("character_concept", "")
        else:
            pages = story_json
            character_concept = ""

        # Save readable story
        output_story_path = OUTPUT_DIR / "story.txt"
        with open(output_story_path, "w") as f:
            if character_concept:
                f.write(f"--- CHARACTER CONCEPT ---\n{character_concept}\n\n")
            
            for page, text in pages.items():
                f.write(f"--- {page.upper()} ---\n\n")
                f.write(text)
                f.write("\n\n")
        
        console.print(f"[green]Story saved to '{output_story_path}'[/green]")
        
    except Exception as e:
        console.print(f"[bold red]Error generating story: {e}[/bold red]")
        raise typer.Exit(code=1)

    # 5. Generate Images
    console.print("[bold cyan]Generating Images...[/bold cyan]")
    try:
        with open("comic.md", "r") as f:
            style_prompt = f.read()
            
        for page, text in pages.items():
            console.print(f"Generating image for {page}...")
            
            # Integrate character concept into the prompt
            full_prompt = f"{style_prompt}\n\n"
            if character_concept:
                full_prompt += f"CHARACTER SHEET / MASTER VISUAL ANCHOR:\n{character_concept}\n\n"
            
            full_prompt += f"Scene Context:\n{text}"
            
            # Use the no-audio files for image generation
            response = generate_content_with_retry(
                model="gemini-3-pro-image-preview",
                contents=[full_prompt] + uploaded_files_images,
                config=types.GenerateContentConfig(
                    seed=42,
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                        image_size="2K"
                    )
                )
            )
            
            # Extract image data from candidates
            image_data = None
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        image_data = part.inline_data.data
                        break
            
            if image_data:
                 # Save image
                image_path = OUTPUT_DIR / f"{page}.png"
                with open(image_path, "wb") as f:
                    f.write(image_data)
                console.print(f"[green]Saved {image_path}[/green]")
            else:
                 console.print(f"[red]No image generated for {page}[/red]")
                 console.print(response.text)

    except Exception as e:
        console.print(f"[bold red]Error generating images: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print(Panel.fit("[bold green]Process Complete![/bold green]"))

if __name__ == "__main__":
    app()
