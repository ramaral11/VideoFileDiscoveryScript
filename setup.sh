#!/bin/bash
# Setup script for slate detection tool on WSL2 (Ubuntu 22.04)

echo "Setting up Slate Detection Tool..."
echo "=================================="

# Update package list
echo "Updating package list..."
sudo apt update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    libopencv-dev \
    python3-opencv \
    git

# Create virtual environment
echo "Creating Python virtual environment..."
python3 -m venv slate_detector_env

# Activate virtual environment
source slate_detector_env/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install \
    opencv-python \
    numpy \
    tqdm \
    Pillow

# Create requirements.txt
cat > requirements.txt << EOF
opencv-python>=4.8.0
numpy>=1.24.0
tqdm>=4.65.0
Pillow>=9.5.0
EOF

# Make the script executable
chmod +x slate_detector.py

# Create example usage script
cat > run_example.sh << 'EOF'
#!/bin/bash
# Example usage of the slate detector

# Activate virtual environment
source slate_detector_env/bin/activate

# Run the detector
# Replace /path/to/videos with your actual video folder path
python3 slate_detector.py /path/to/videos -o ./slate_output -t 0.8 -w 4

# Deactivate virtual environment
deactivate
EOF

chmod +x run_example.sh

echo ""
echo "Setup complete!"
echo ""
echo "Usage:"
echo "  1. Activate the virtual environment: source slate_detector_env/bin/activate"
echo "  2. Run the detector: python3 slate_detector.py /path/to/videos"
echo "  3. Or use the example script: ./run_example.sh (edit the path first)"
echo ""
echo "For help: python3 slate_detector.py --help"