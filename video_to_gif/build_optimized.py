import PyInstaller.__main__
import os
import shutil

# Define the build parameters
app_name = "TechGifConverter_Lite"
main_script = os.path.join("src", "main.py")
icon_path = "" # Add icon path if available

# Clean up previous builds
if os.path.exists("build"):
    shutil.rmtree("build")
if os.path.exists("dist"):
    shutil.rmtree("dist")

# PyInstaller arguments
args = [
    main_script,
    '--name=%s' % app_name,
    '--onefile',          # Create a single executable
    '--windowed',         # No console window
    '--clean',            # Clean cache
    '--noconfirm',        # Do not confirm overwrite
    
    # Path configuration
    '--paths=src',
    
    # Exclude unnecessary standard libraries and packages to reduce size
    '--exclude-module=tkinter',
    '--exclude-module=matplotlib',
    '--exclude-module=scipy',
    '--exclude-module=pandas',
    '--exclude-module=numpy',      # Risky: check if moviepy needs it. Moviepy typically needs numpy.
                                   # If the app fails, remove this exclude.
                                   # EDIT: moviepy heavily relies on numpy. CANNOT exclude numpy.
    '--exclude-module=cv2',        # We confirmed this is unused
    '--exclude-module=PIL',        # Moviepy uses pillow, so we probably need this
    '--exclude-module=pydoc',
    '--exclude-module=lib2to3',
    '--exclude-module=xml.dom',
    '--exclude-module=xml.sax',
]

# Note on Numpy: MoviePy depends on Numpy. We cannot exclude it.
# However, we can try to exclude mkl if it's installed/picked up, but that's harder to control via args.

# Run PyInstaller
print("Starting build process...")
print(f"Arguments: {args}")

# Filter out the numpy exclude for safety as it creates broken apps for moviepy
safe_args = [arg for arg in args if 'numpy' not in arg]

PyInstaller.__main__.run(safe_args)

print(f"Build complete. Check the 'dist' folder for {app_name}.exe")
