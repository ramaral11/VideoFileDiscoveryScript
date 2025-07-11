#!/bin/bash
# Setup script for slate detection tool on WSL2 (Ubuntu 22.04)

echo "Setting up Slate Detection Tool..."
echo "=================================="

# Check if we're on a network mount (which can cause issues with symlinks)
CURRENT_DIR=$(pwd)
if [[ "$CURRENT_DIR" == /mnt/* ]]; then
    echo "WARNING: Running from a network mount. Virtual environment will be created in /tmp instead."
    VENV_DIR="/tmp/slate_detector_env_$$"
else
    VENV_DIR="./slate_detector_env"
fi

# Update package list
echo "Updating package list..."
sudo apt update

# Install system dependencies including python3-full for newer Ubuntu versions
echo "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    ffmpeg \
    libopencv-dev \
    python3-opencv \
    git

# Create virtual environment with proper error handling
echo "Creating Python virtual environment..."
if ! python3 -m venv "$VENV_DIR" --system-site-packages; then
    echo "Failed to create virtual environment. Trying alternative method..."
    # Try without symlinks if on network mount
    if ! python3 -m venv "$VENV_DIR" --without-pip --system-site-packages; then
        echo "ERROR: Could not create virtual environment"
        exit 1
    fi
    # Manually ensure pip is available
    curl https://bootstrap.pypa.io/get-pip.py | "$VENV_DIR/bin/python3"
fi

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "ERROR: Virtual environment activation script not found"
    exit 1
fi

# Install Python dependencies
echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install \
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

# Create example usage script with proper venv path
cat > run_example.sh << EOF
#!/bin/bash
# Example usage of the slate detector

# Virtual environment location
VENV_DIR="$VENV_DIR"

# Activate virtual environment
if [ -f "\$VENV_DIR/bin/activate" ]; then
    source "\$VENV_DIR/bin/activate"
else
    echo "ERROR: Virtual environment not found at \$VENV_DIR"
    exit 1
fi

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
echo "Virtual environment created at: $VENV_DIR"
echo ""
echo "Usage:"
echo "  1. Activate the virtual environment: source $VENV_DIR/bin/activate"
echo "  2. Run the detector: python3 slate_detector.py /path/to/videos"
echo "  3. Or use the example script: ./run_example.sh (edit the path first)"
echo ""
echo "For help: python3 slate_detector.py --help"

# If we created venv in /tmp, remind user
if [[ "$VENV_DIR" == /tmp/* ]]; then
    echo ""
    echo "NOTE: Virtual environment was created in /tmp due to network mount."
    echo "      It will be removed on system restart. Run setup again if needed."
fi