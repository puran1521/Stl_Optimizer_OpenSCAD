import os
import subprocess
import zipfile
from tkinter import Tk, filedialog, Label, Entry, Button, OptionMenu, StringVar

def optimize_stl(input_path, thickness=0.2, max_speed=100, mode="fast", output_dir=""):
    # Dimensions (30x30x30 mm cube)
    dims = [30.0, 30.0, 30.0]
    print(f"Assumed Dimensions: X={dims[0]:.2f}, Y={dims[1]:.2f}, Z={dims[2]:.2f} mm")

    # Check thickness
    min_dim = min(dims)
    if thickness > min_dim / 2:
        print(f"Error: Thickness {thickness} exceeds half of smallest dimension ({min_dim:.2f})")
        return False

    # Generate OpenSCAD script
    scad_script = f"""
    module cube_model() {{
        import("{input_path.replace('\\', '/')}");  // Load STL
    }}

    // Center the cube at origin (assuming it’s not centered)
    translate([-15, -15, -15])  // Move to [-15, -15, -15] to [15, 15, 15]
    difference() {{
        cube_model();  // Outer shell
        scale([{(dims[0] - 2*thickness)/dims[0]}, {(dims[1] - 2*thickness)/dims[1]}, {(dims[2] - 2*thickness)/dims[2]}])
            cube_model();  // Inner shell
        translate([15, 15, -0.01])  // Cut just below z=0
            cube([31, 31, 0.02]);  // Thin bottom cut, not centered
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

    # Volume (approximate)
    orig_volume = dims[0] * dims[1] * dims[2]
    inner_dims = [max(d - 2 * thickness, 0) for d in dims]
    opt_volume = orig_volume - (inner_dims[0] * inner_dims[1] * inner_dims[2])
    print(f"Thickness {thickness}: Original Volume: {orig_volume:.2f} mm³")
    print(f"Optimized Volume: {opt_volume:.2f} mm³")
    print(f"Final Height: {dims[2]:.2f} mm")

    # Generate Cura profile as .curaprofile
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
acceleration_print = 2000
cool_min_layer_time = 0
infill_sparse_density = 2
jerk_print = 30
speed_print = {max_speed}
speed_wall_0 = {max_speed}
speed_wall_x = {max_speed}
wall_thickness = {thickness}
print_thin_walls = True
layer_height = 0.2
top_thickness = 1.2
support_enable = False
"""

    # Create .curaprofile ZIP
    profile_path = output_path.replace(".stl", ".curaprofile")
    with zipfile.ZipFile(profile_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("anycubic_kobra_max_test", global_ini)
        zf.writestr("anycubic_kobra_max_extruder_0_#2_test", extruder_ini)
    print(f"Exported Cura Profile: {profile_path}")
    print(f"Instructions: Load '{os.path.basename(output_path)}' into Cura, then import '{os.path.basename(profile_path)}' (File > Open Profile).")
    print(f"Estimated Print Time: ~{int(23 - (max_speed / 200) * 6)} min (saves ~{int((200 - max_speed) / 200 * 6)} min).")
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