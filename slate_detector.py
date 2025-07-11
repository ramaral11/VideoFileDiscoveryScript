#!/usr/bin/env python3
"""
Video Slate Detection Script
Detects slates (black frames with white text) in the first frames of video files
and exports them as PNG images with metadata mapping.
"""

import os
import sys
import json
import argparse
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Supported video formats
VIDEO_EXTENSIONS = {
    '.mp4', '.mxf', '.mov', '.avi', '.mkv', '.wmv', 
    '.flv', '.webm', '.m4v', '.mpg', '.mpeg', '.3gp',
    '.f4v', '.ogv', '.vob', '.ts', '.m2ts', '.mts'
}

class SlateDetector:
    def __init__(self, input_folder, output_folder, frames_to_check=60, threshold=0.8, target_frame=20, once_per_folder=False):
        """
        Initialize the slate detector.
        
        Args:
            input_folder: Root folder to search for videos
            output_folder: Folder to save PNG images and metadata
            frames_to_check: Number of frames to check (2 seconds @ 30fps = 60 frames)
            threshold: Confidence threshold for slate detection (0-1)
            target_frame: Specific frame to check first (default: 20)
            once_per_folder: Only save first slate per subfolder (default: False)
        """
        self.input_folder = Path(input_folder).resolve()
        self.output_folder = Path(output_folder).resolve()
        self.frames_to_check = frames_to_check
        self.threshold = threshold
        self.target_frame = target_frame
        self.once_per_folder = once_per_folder
        self.metadata = {}
        self.saved_folders = set()  # Track folders that already have a slate saved
        
        # Create output folder if it doesn't exist
        self.output_folder.mkdir(parents=True, exist_ok=True)
        
    def find_video_files(self):
        """Recursively find all video files in the input folder."""
        video_files = []
        
        for ext in VIDEO_EXTENSIONS:
            video_files.extend(self.input_folder.rglob(f'*{ext}'))
            video_files.extend(self.input_folder.rglob(f'*{ext.upper()}'))
        
        return sorted(set(video_files))
    
    def is_slate_frame(self, frame):
        """
        Detect if a frame is a slate (black background with white text).
        
        Args:
            frame: OpenCV frame (numpy array)
            
        Returns:
            tuple: (is_slate, confidence_score)
        """
        if frame is None:
            return False, 0.0
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate histogram
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        
        # Normalize histogram
        hist = hist.flatten() / hist.sum()
        
        # Check if image is mostly black (high concentration of dark pixels)
        black_pixels_ratio = hist[:30].sum()  # Pixels with values 0-30
        
        # Apply threshold to get binary image
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # Calculate white pixels ratio (potential text)
        white_pixels_ratio = np.sum(binary == 255) / binary.size
        
        # Detect if it's a slate (more lenient criteria):
        # - Most pixels should be black (>50%)
        # - Some white pixels for text (0.5-40%)
        # - High contrast between black and white areas
        is_slate = (
            black_pixels_ratio > 0.5 and
            0.005 < white_pixels_ratio < 0.4
        )
        
        # Calculate confidence score
        if is_slate:
            # Check for text-like patterns using edge detection
            edges = cv2.Canny(gray, 50, 150)
            edge_ratio = np.sum(edges > 0) / edges.size
            
            # Confidence based on expected characteristics
            confidence = min(
                black_pixels_ratio * 0.4 +  # Black background weight
                (1 - abs(white_pixels_ratio - 0.1) * 5) * 0.4 +  # Optimal text coverage
                edge_ratio * 0.2  # Edge presence
            , 1.0)
        else:
            confidence = 0.0
        
        return is_slate, confidence
    
    def process_video(self, video_path):
        """
        Process a single video file to detect slates.
        
        Args:
            video_path: Path to the video file
            
        Returns:
            dict: Processing result with slate information
        """
        relative_path = video_path.relative_to(self.input_folder)
        result = {
            'video_path': str(relative_path),
            'slate_found': False,
            'confidence': 0.0,
            'frame_number': -1,
            'error': None
        }
        
        try:
            # Open video file
            cap = cv2.VideoCapture(str(video_path))
            
            if not cap.isOpened():
                result['error'] = 'Failed to open video file'
                return result
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS) or 30  # Default to 30 fps if not available
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Calculate target frame (default: frame 20 at ~0.8 seconds for 25fps)
            # This avoids fade-ins and catches the slate before the 1s black transition
            target_frame = min(self.target_frame, total_frames - 1)
            
            best_slate_frame = None
            best_confidence = 0.0
            best_frame_number = -1
            
            # First, try to check the target frame (frame 20)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            if ret:
                is_slate, confidence = self.is_slate_frame(frame)
                if is_slate and confidence >= self.threshold:
                    # Found a good slate at the target frame
                    best_slate_frame = frame.copy()
                    best_confidence = confidence
                    best_frame_number = target_frame
                    logger.debug(f"Found slate at target frame {target_frame} with confidence {confidence:.3f}")
            
            # If no good slate at target frame, check other frames
            if best_confidence < self.threshold:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to beginning
                frames_to_check = min(self.frames_to_check, int(fps * 2), total_frames)
                
                for frame_num in range(frames_to_check):
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    is_slate, confidence = self.is_slate_frame(frame)
                    
                    if is_slate and confidence > best_confidence:
                        best_slate_frame = frame.copy()
                        best_confidence = confidence
                        best_frame_number = frame_num
            
            cap.release()
            
            # Log diagnostic info for debugging
            if best_confidence > 0:
                logger.debug(f"Best slate candidate in {relative_path}: frame {best_frame_number}, "
                           f"confidence {best_confidence:.3f} (threshold: {self.threshold})")
            
            # If slate found with sufficient confidence
            if best_confidence >= self.threshold:
                result['slate_found'] = True
                result['confidence'] = float(best_confidence)
                result['frame_number'] = best_frame_number
                result['timestamp'] = best_frame_number / fps
                
                # Check if we should save this slate image
                video_folder = video_path.parent
                should_save = True
                
                if self.once_per_folder:
                    # Check if we've already saved a slate from this folder
                    if video_folder in self.saved_folders:
                        should_save = False
                        logger.info(f"Slate found in {relative_path} but skipping save (already have slate from this folder)")
                    else:
                        self.saved_folders.add(video_folder)
                
                if should_save:
                    # Generate unique filename
                    video_hash = hashlib.md5(str(video_path).encode()).hexdigest()[:8]
                    png_filename = f"slate_{video_hash}_{best_frame_number:04d}.png"
                    png_path = self.output_folder / png_filename
                    
                    # Save the slate frame
                    cv2.imwrite(str(png_path), best_slate_frame)
                    result['png_filename'] = png_filename
                    
                    logger.info(f"Slate found and saved in {relative_path} at frame {best_frame_number} "
                              f"(confidence: {best_confidence:.2f})")
                else:
                    result['png_filename'] = None  # Slate found but not saved
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error processing {relative_path}: {e}")
        
        return result
    
    def process_videos_parallel(self, video_files, max_workers=None):
        """
        Process multiple videos in parallel.
        
        Args:
            video_files: List of video file paths
            max_workers: Maximum number of parallel workers
        """
        results = []
        
        # Use ProcessPoolExecutor for CPU-bound tasks
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_video = {
                executor.submit(self.process_video, video): video 
                for video in video_files
            }
            
            # Process completed tasks with progress bar
            with tqdm(total=len(video_files), desc="Processing videos") as pbar:
                for future in as_completed(future_to_video):
                    video = future_to_video[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Failed to process {video}: {e}")
                        results.append({
                            'video_path': str(video.relative_to(self.input_folder)),
                            'slate_found': False,
                            'error': str(e)
                        })
                    pbar.update(1)
        
        return results
    
    def save_metadata(self, results):
        """Save metadata to JSON file."""
        metadata = {
            'scan_date': datetime.now().isoformat(),
            'input_folder': str(self.input_folder),
            'output_folder': str(self.output_folder),
            'total_videos_scanned': len(results),
            'slates_found': sum(1 for r in results if r['slate_found']),
            'videos': results
        }
        
        metadata_path = self.output_folder / 'slate_metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Metadata saved to {metadata_path}")
        
        # Also create a simple mapping file
        mapping = {}
        for result in results:
            if result['slate_found'] and result.get('png_filename'):
                mapping[result['png_filename']] = {
                    'video_path': result['video_path'],
                    'frame_number': result['frame_number'],
                    'timestamp': result['timestamp'],
                    'confidence': result['confidence']
                }
        
        mapping_path = self.output_folder / 'slate_mapping.json'
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
        
        return metadata

def main():
    parser = argparse.ArgumentParser(
        description='Detect slates in video files and export as PNG images'
    )
    parser.add_argument(
        'input_folder',
        help='Root folder containing video files'
    )
    parser.add_argument(
        '-o', '--output',
        default='./slate_output',
        help='Output folder for PNG files and metadata (default: ./slate_output)'
    )
    parser.add_argument(
        '-f', '--frames',
        type=int,
        default=60,
        help='Number of frames to check (default: 60)'
    )
    parser.add_argument(
        '-t', '--threshold',
        type=float,
        default=0.8,
        help='Confidence threshold for slate detection (0-1, default: 0.8)'
    )
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=None,
        help='Number of parallel workers (default: auto)'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging to see detection details'
    )
    parser.add_argument(
        '--target-frame',
        type=int,
        default=20,
        help='Specific frame number to check first (default: 20, ~0.8s at 25fps)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Only save the first slate image per subfolder (all slates still registered in metadata)'
    )
    
    args = parser.parse_args()
    
    # Enable debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate input folder
    if not os.path.exists(args.input_folder):
        logger.error(f"Input folder does not exist: {args.input_folder}")
        sys.exit(1)
    
    # Create detector instance
    detector = SlateDetector(
        args.input_folder,
        args.output,
        args.frames,
        args.threshold,
        args.target_frame,
        args.once
    )
    
    # Find video files
    logger.info(f"Searching for video files in: {args.input_folder}")
    video_files = detector.find_video_files()
    
    if not video_files:
        logger.warning("No video files found!")
        sys.exit(0)
    
    logger.info(f"Found {len(video_files)} video files")
    
    # Process videos
    results = detector.process_videos_parallel(video_files, args.workers)
    
    # Save metadata
    metadata = detector.save_metadata(results)
    
    # Print summary
    print("\n" + "="*50)
    print("PROCESSING SUMMARY")
    print("="*50)
    print(f"Total videos scanned: {metadata['total_videos_scanned']}")
    print(f"Slates found: {metadata['slates_found']}")
    if detector.once_per_folder:
        images_saved = sum(1 for r in results if r['slate_found'] and r.get('png_filename'))
        print(f"Images saved: {images_saved} (--once mode: first per folder)")
    print(f"Output folder: {detector.output_folder}")
    print(f"Metadata file: {detector.output_folder / 'slate_metadata.json'}")
    print(f"Mapping file: {detector.output_folder / 'slate_mapping.json'}")
    
    # List videos with slates
    if metadata['slates_found'] > 0:
        print("\nVideos with slates detected:")
        for result in results:
            if result['slate_found']:
                print(f"  - {result['video_path']} "
                      f"(frame {result['frame_number']}, "
                      f"confidence: {result['confidence']:.2f})")

if __name__ == "__main__":
    main()