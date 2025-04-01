import os
import subprocess
import zipfile
import trimesh
from tkinter import Tk, filedialog, Label, Entry, Button, OptionMenu, StringVar

def optimize_stl(input_path, thickness=0.2, max_speed=150, mode="fast", output_dir=""):
    # Load STL
    mesh = trimesh.load(input_path)
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
    if thickness > min_dim / 2:
        thickness = min_dim / 4
        print(f"Adjusted thickness to {thickness:.2f} mm to fit model dimensions.")

    # Generate OpenSCAD script
    scad_script = f"""
    module model() {{
        translate([{-center[0]}, {-center[1]}, {-center[2]}])  // Center at origin
        import("{input_path.replace('\\', '/')}");  // Load STL
    }}

    difference() {{
        model();  // Outer shell
        scale([{(dims[0] - 2*thickness)/dims[0]}, {(dims[1] - 2*thickness)/dims[1]}, {(dims[2] - 2*thickness)/dims[2]}])
            model();  // Inner shell
        translate([0, 0, {bounds[0][2] - 0.01}])  // Bottom face
            cube([{dims[0] + 1}, {dims[1] + 1}, 0.02], center=true);  // Thin bottom cut
    }}
    """
    scad_path = os.path.join(output_dir, "temp.scad")
    with open(scad_path, "w") as f:
        f.write(scad_script)

    # Run OpenSCAD
    output_path = os.path.join(output_dir, os.path.basename(input_path).replace(".stl", f"_opt_t{thickness}_m{mode}.stl"))
    openscad_path = "openscad"  # Adjust if bundled
    try:
        subprocess.run([openscad_path, "-o", output_path, scad_path], check=True)
        os.remove(scad_path)
        print(f"Exported STL: {output_path}")
    except subprocess.CalledProcessError:
        print("Error: OpenSCAD failed—check installation or STL file.")
        os.remove(scad_path)
        return False

    # Volume
    orig_volume = dims[0] * dims[1] * dims[2]
    inner_dims = [max(d - 2 * thickness, 0) for d in dims]
    opt_volume = orig_volume - (inner_dims[0] * inner_dims[1] * inner_dims[2])
    print(f"Thickness {thickness}: Original Volume: {orig_volume:.2f} mm³")
    print(f"Optimized Volume: {opt_volume:.2f} mm³")
    print(f"Final Height: {dims[2]:.2f} mm")

    # Cura profile with fixed user max speed
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
infill_sparse_density = 2
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
    print(f"Instructions: Load '{os.path.basename(output_path)}' into Cura, then import '{os.path.basename(profile_path)}' (File > Open Profile).")
    return True

# GUI
def run_gui():
    root = Tk()
    root.title("PrintFast STL Optimizer (OpenSCAD)")
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