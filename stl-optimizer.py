import os
import subprocess
import zipfile
import trimesh
import tempfile
from tkinter import Tk, filedialog, Label, Entry, Button, OptionMenu, StringVar

# CuraEngine path (adjust based on your Cura installation)
CURA_ENGINE_PATH = r"C:\Program Files\UltiMaker Cura 5.9.1\CuraEngine.exe"
# Base definition file for Anycubic Kobra Max (assumed in Cura’s resources)
BASE_DEF = r"C:\Program Files\UltiMaker Cura 5.9.1\share\cura\resources\definitions\anycubic_kobra_max.def.json"

def optimize_stl(input_path, thickness=0.2, max_speed=150, mode="fast", output_dir=""):
    # Load STL and validate
    try:
        mesh = trimesh.load(input_path)
        if not mesh.is_watertight:
            print("Warning: STL is not watertight—optimization may fail.")
    except Exception as e:
        print(f"Error loading STL: {e}")
        return False

    bounds = mesh.bounds
    dims = [bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1], bounds[1][2] - bounds[0][2]]
    center = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2, (bounds[0][2] + bounds[1][2]) / 2]
    
    # Scale if tiny (< 1 mm)
    scale_factor = 1000 if max(dims) < 1 else 1
    if scale_factor != 1:
        dims = [d * scale_factor for d in dims]
        center = [c * scale_factor for c in center]
        bounds = [[b * scale_factor for b in bounds[0]], [b * scale_factor for b in bounds[1]]]
        print(f"Scaled model by {scale_factor}x—assuming input was in meters.")
    
    print(f"Actual Dimensions: X={dims[0]:.2f}, Y={dims[1]:.2f}, Z={dims[2]:.2f} mm")
    print(f"Center: X={center[0]:.2f}, Y={center[1]:.2f}, Z={center[2]:.2f} mm")

    # Adjust thickness
    min_dim = min(dims)
    if thickness * 2 > min_dim:
        thickness = min_dim / 4
        print(f"Adjusted thickness to {thickness:.2f} mm to fit model (min dim: {min_dim:.2f} mm).")
    elif thickness < 0.4:
        thickness = 0.4
        print(f"Set thickness to minimum 0.4 mm for printability.")

    if min_dim - 2 * thickness < 0.4:
        print(f"Error: Model too thin (min dim - 2*thickness = {min_dim - 2*thickness:.2f} mm) for hollowing.")
        return False

    # Generate OpenSCAD script
    scad_script = f"""
    module model() {{
        translate([{-center[0]}, {-center[1]}, {-center[2]}])
        import("{input_path.replace('\\', '/')}"); 
    }}

    difference() {{
        model();
        minkowski() {{
            scale([{(dims[0] - 2*thickness)/dims[0]}, {(dims[1] - 2*thickness)/dims[1]}, {(dims[2] - 2*thickness)/dims[2]}])
                model();
            sphere(r=0.01);
        }}
    }}

    difference() {{
        difference() {{
            model();
            minkowski() {{
                scale([{(dims[0] - 2*thickness)/dims[0]}, {(dims[1] - 2*thickness)/dims[1]}, {(dims[2] - 2*thickness)/dims[2]}])
                    model();
                sphere(r=0.01);
            }}
        }}
        translate([0, 0, {bounds[0][2] - 0.001}])
            cube([{dims[0] + 0.1}, {dims[1] + 0.1}, 0.002], center=true);
    }}
    """
    scad_path = os.path.join(output_dir, "temp.scad")
    with open(scad_path, "w") as f:
        f.write(scad_script)

    # Run OpenSCAD
    output_path = os.path.join(output_dir, os.path.basename(input_path).replace(".stl", f"_opt_t{thickness}_m{mode}.stl"))
    openscad_path = "openscad"
    try:
        subprocess.run([openscad_path, "-o", output_path, scad_path], check=True, timeout=300)
        os.remove(scad_path)
        print(f"Exported STL: {output_path}")
    except subprocess.CalledProcessError:
        print("Error: OpenSCAD failed—check STL complexity.")
        os.remove(scad_path)
        return False
    except subprocess.TimeoutExpired:
        print("Error: OpenSCAD timed out.")
        os.remove(scad_path)
        return False

    # Volume check
    orig_volume = mesh.volume * (scale_factor ** 3)
    opt_mesh = trimesh.load(output_path)
    opt_volume = opt_mesh.volume
    print(f"Thickness {thickness}: Original Volume: {orig_volume:.2f} mm³")
    print(f"Optimized Volume: {opt_volume:.2f} mm³")
    print(f"Final Height: {dims[2]:.2f} mm")

    if max(dims) < 10:
        print(f"Warning: Model dimensions {dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f} mm are small—scale in Cura if needed.")
    if opt_volume > orig_volume or abs(orig_volume - opt_volume) < 1:
        print("Warning: Volume check failed—hollowing may be incorrect.")

    # Cura profile
    profile_name = f"PrintFast_{mode}_t{thickness}"
    global_ini = f"""[general]
version = 4
name = {profile_name}
definition = anycubic_kobra_max

[metadata]
type = quality_changes
quality_type = pla
intent_category = default
setting_version = 24

[values]
"""

    extruder_ini = f"""[general]
version = 4
name = {profile_name}
definition = anycubic_kobra_max

[metadata]
type = quality_changes
quality_type = pla
intent_category = default
position = 0
setting_version = 24

[values]
acceleration_print = 3000
cool_min_layer_time = 0
infill_sparse_density = 10
infill_pattern = gyroid
infill_overlap = 10
jerk_print = 40
speed_print = {max_speed}
speed_wall_0 = {max_speed}
speed_wall_x = {max_speed}
wall_thickness = {thickness}
print_thin_walls = True
layer_height = 0.2
top_thickness = 1.2
support_enable = False
"""

    # Create .curaprofile
    profile_path = output_path.replace(".stl", ".curaprofile")
    with zipfile.ZipFile(profile_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("anycubic_kobra_max_test", global_ini)
        zf.writestr("anycubic_kobra_max_extruder_0_#2_test", extruder_ini)
    print(f"Exported Cura Profile: {profile_path}")

    # Slice with CuraEngine
    def get_print_time(stl_path, profile_path, label):
        if not os.path.exists(CURA_ENGINE_PATH):
            print(f"Error: CuraEngine not found at {CURA_ENGINE_PATH}")
            return None
        if not os.path.exists(BASE_DEF):
            print(f"Error: Base definition file not found at {BASE_DEF}")
            return None
        
        temp_gcode = os.path.join(tempfile.gettempdir(), f"temp_{label}.gcode")
        cmd = [
            CURA_ENGINE_PATH, "slice",
            "-v",  # Verbose output
            "-j", BASE_DEF,
            "-s", f"print_sequence=one_at_a_time",
            "-l", stl_path,
            "-o", temp_gcode,
            "-e0", f"load={profile_path}"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            output = result.stdout
            for line in output.splitlines():
                if ";TIME:" in line:
                    time_sec = int(line.split(":")[1])
                    os.remove(temp_gcode)
                    return time_sec / 60  # Convert to minutes
            print(f"Error: Print time not found in CuraEngine output for {label}")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Error slicing {label}: {e.stderr}")
            return None

    # Calculate times
    opt_time = get_print_time(output_path, profile_path, "optimized")
    unopt_time = get_print_time(input_path, profile_path, "unoptimized")
    
    if opt_time is not None:
        print(f"Optimized Print Time: {opt_time:.2f} minutes")
    if unopt_time is not None:
        print(f"Unoptimized Print Time: {unopt_time:.2f} minutes")
    if opt_time and unopt_time:
        print(f"Time Saved: {unopt_time - opt_time:.2f} minutes ({(unopt_time - opt_time) / unopt_time * 100:.1f}%)")

    print(f"Instructions: Load '{os.path.basename(output_path)}' into Cura, then import '{os.path.basename(profile_path)}' for verification.")
    return True

# GUI
def run_gui():
    root = Tk()
    root.title("PrintFast STL Optimizer (OpenSCAD + Cura)")
    root.geometry("400x300")

    Label(root, text="Optimize Your 3D Print!", font=("Arial", 14)).pack(pady=10)

    stl_path = StringVar()
    Label(root, text="Select STL File:").pack()
    Button(root, text="Browse", command=lambda: stl_path.set(filedialog.askopenfilename(filetypes=[("STL Files", "*.stl")]))).pack()
    Entry(root, textvariable=stl_path, width=40).pack()

    speed_var = StringVar(value="150")
    Label(root, text="Printer Max Speed (mm/s):").pack()
    Entry(root, textvariable=speed_var, width=10).pack()

    mode_var = StringVar(value="fast")
    Label(root, text="Mode:").pack()
    OptionMenu(root, mode_var, "fast", "balanced").pack()

    def optimize():
        input_path = stl_path.get()
        if not input_path:
            print("Error: No STL file selected!")
            return
        max_speed = int(speed_var.get())
        mode = mode_var.get()
        thickness = 0.2 if mode == "fast" else 0.8
        output_dir = os.path.dirname(input_path)
        if optimize_stl(input_path, thickness, max_speed, mode, output_dir):
            print("Optimization complete! Check output files in", output_dir)

    Button(root, text="Optimize!", command=optimize, bg="green", fg="white", font=("Arial", 12)).pack(pady=20)

    root.mainloop()

if __name__ == "__main__":
    run_gui()