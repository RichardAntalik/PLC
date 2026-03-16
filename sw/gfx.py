from PIL import Image, ImageDraw, ImageFont, ImageSequence
import time
import os
import mmap
import numpy as np
import sys

# Linux Framebuffer Constants
FBIOGET_VSCREENINFO = 0x4600

class Animation:
    """
    A simplified, time-based animation asset.
    It doesn't store 'current state' but calculates the correct frame 
    based on the current timestamp.
    """
    def __init__(self, source, fps=10):
        self.frames = []
        self.fps = fps
        
        # Load frames (supports list of images, directories, or GIFs)
        if isinstance(source, list):
             self.frames = source
        elif os.path.isdir(source):
            valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
            files = sorted([f for f in os.listdir(source) if os.path.splitext(f)[1].lower() in valid_exts])
            for f in files:
                try:
                    img = Image.open(os.path.join(source, f)).convert("RGBA")
                    self.frames.append(img)
                except IOError: pass 
        elif os.path.isfile(source):
            try:
                gif = Image.open(source)
                for frame in ImageSequence.Iterator(gif):
                    self.frames.append(frame.copy().convert("RGBA"))
            except IOError:
                raise ValueError(f"Could not open animation file: {source}")
        else:
            raise ValueError(f"Source not found or invalid: {source}")

        if not self.frames:
            raise ValueError(f"No valid images found in {source}")
            
        self.duration = len(self.frames) / fps if fps > 0 else 0

    def get_frame_at_time(self, timestamp):
        """Returns the specific PIL Image for the given timestamp."""
        if not self.frames: return None
        if self.duration == 0: return self.frames[0]
        
        # Calculate index based on time
        # The modulo operator (%) creates the looping effect
        cycle_t = timestamp % self.duration
        frame_idx = int(cycle_t * self.fps) % len(self.frames)
        return self.frames[frame_idx]

class Gfx:
    def __init__(self, fb_device='/dev/fb0'):
        self.fb_device = fb_device
        self._font_cache = {}
        self._image_cache = {}      # Cache for static images
        self._animation_cache = {}  # Cache for animations
        
        # Detect Screen Configuration
        self.width, self.height, self.bpp = self._get_fb_info()
        print(f"GFX Init: Display detected at {self.width}x{self.height} ({self.bpp}-bit)")

        # Open Framebuffer
        try:
            self._fb_file = open(self.fb_device, 'r+b')
            self._fb_fd = self._fb_file.fileno()
        except OSError as e:
            raise RuntimeError(f"Could not open framebuffer {fb_device}. Error: {e}")

        # Map memory
        self._frame_bytes = self.width * self.height * (self.bpp // 8)
        self.fb_mmap = mmap.mmap(self._fb_fd, self._frame_bytes)

        # Save framebuffer state
        self.fb_mmap.seek(0)
        self._saved_framebuffer = self.fb_mmap.read(self._frame_bytes)

        # Setup Canvas
        self.background = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 255))
        self._canvas = Image.new("RGBA", (self.width, self.height))
        self._draw = ImageDraw.Draw(self._canvas)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _get_fb_info(self):
        dev_name = os.path.basename(self.fb_device)
        sys_path = f"/sys/class/graphics/{dev_name}"
        try:
            with open(f"{sys_path}/virtual_size", "r") as f:
                w, h = map(int, f.read().strip().split(","))
            with open(f"{sys_path}/bits_per_pixel", "r") as f:
                bpp = int(f.read().strip())
            return w, h, bpp
        except FileNotFoundError:
            raise RuntimeError(f"Could not read system info for {dev_name}.")

    def _get_font(self, font_path, font_size):
        if font_path is None:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

        key = (font_path, font_size)
        if key not in self._font_cache:
            try:
                font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
            except IOError:
                font = ImageFont.load_default()
            self._font_cache[key] = font
        return self._font_cache[key]

    def set_background(self, source):
        if isinstance(source, tuple):
            self.background = Image.new("RGBA", (self.width, self.height), source + (255,))
        elif isinstance(source, str):
            img = Image.open(source).convert("RGBA")
            # Scale and crop logic
            image_ratio = img.width / img.height
            screen_ratio = self.width / self.height
            if screen_ratio < image_ratio:
                scaled_width = img.width * self.height // img.height
                scaled_height = self.height
            else:
                scaled_width = self.width
                scaled_height = img.height * self.width // img.width
            img = img.resize((scaled_width, scaled_height), Image.BICUBIC)
            
            x = scaled_width // 2 - self.width // 2
            y = scaled_height // 2 - self.height // 2
            img = img.crop((x, y, x + self.width, y + self.height))
            self.background = img
        elif isinstance(source, Image.Image):
            self.background = source.convert("RGBA").resize((self.width, self.height))

    # --- New Animation Helpers ---
    def load_animation(self, path, fps=10):
        """Explicitly loads an animation asset (optional, can just use draw_animation with path)."""
        return Animation(path, fps)

    def clear(self):
        self._canvas.paste(self.background, (0, 0))

    def draw_image(self, source, x, y):
        """
        Draws an image at x, y. 
        'source' can be a file path (str) or a PIL Image.
        Files are automatically cached.
        """
        img = None
        if isinstance(source, str):
            if source not in self._image_cache:
                try:
                    self._image_cache[source] = Image.open(source).convert("RGBA")
                except IOError:
                    print(f"Error loading image: {source}")
                    return
            img = self._image_cache[source]
        else:
            img = source
            
        if img:
            self._canvas.paste(img, (int(x), int(y)), mask=img if img.mode == 'RGBA' else None)

    def draw_animation(self, source, x, y, timestamp=None, fps=10):
        """
        Draws the correct frame of an animation based on time.
        'source' can be:
          - A file path (str) to a GIF or folder (cached automatically)
          - An Animation object
          - A list of PIL Images
        """
        if timestamp is None:
            timestamp = time.time()
        
        anim = None
        
        # 1. Resolve Source to Animation Object (with caching for paths)
        if isinstance(source, str):
            # Check Cache
            cache_key = (source, fps)
            if cache_key not in self._animation_cache:
                try:
                    self._animation_cache[cache_key] = Animation(source, fps)
                except Exception as e:
                    print(f"Error loading animation {source}: {e}")
                    return
            anim = self._animation_cache[cache_key]
        elif isinstance(source, Animation):
            anim = source
        elif isinstance(source, list):
             # Ad-hoc list wrapper
            anim = Animation(source, fps)

        # 2. Draw
        if anim:
            img = anim.get_frame_at_time(timestamp)
            if img:
                self._canvas.paste(img, (int(x), int(y)), mask=img)

    def draw_text(self, text, x, y, font_path=None, font_size=20, color=(255, 255, 255)):
        font = self._get_font(font_path, font_size)
        self._draw.text((int(x), int(y)), text, font=font, fill=color)

    def update(self):
        self.fb_mmap.seek(0)
        
        if self.bpp == 16:
            img_rgb = self._canvas.convert("RGB")
            arr = np.array(img_rgb, dtype=np.uint16)
            r = arr[:, :, 0]
            g = arr[:, :, 1]
            b = arr[:, :, 2]
            pixel_data = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            self.fb_mmap.write(pixel_data.tobytes())

        elif self.bpp == 32:
            pixel_bytes = self._canvas.tobytes("raw", "BGRA")
            self.fb_mmap.write(pixel_bytes)
            
        elif self.bpp == 24:
             pixel_bytes = self._canvas.convert("RGB").tobytes("raw", "BGR")
             self.fb_mmap.write(pixel_bytes)

    def refresh(self):
        self.update()
        
    def close(self):
        print("Cleaning up GFX resources...")
        if hasattr(self, 'fb_mmap') and self.fb_mmap is not None:
            if hasattr(self, '_saved_framebuffer') and self._saved_framebuffer:
                try:
                    self.fb_mmap.seek(0)
                    self.fb_mmap.write(self._saved_framebuffer)
                    print("Terminal state restored.")
                except ValueError: pass
            try:
                self.fb_mmap.close()
            except ValueError: pass 
            self.fb_mmap = None

        if hasattr(self, '_fb_file') and self._fb_file is not None:
            try:
                self._fb_file.close()
            except ValueError: pass 
            self._fb_file = None