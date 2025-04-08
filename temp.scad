
    module model() {
        translate([-0.8245000839233398, -0.0, -24.0])
        import("D:/Stl_Optimizer_Openscad/3DBenchy.stl"); 
    }

    difference() {
        model();
        minkowski() {
            scale([0.9866668891869602, 0.9741968775809327, 0.9833333333333334])
                model();
            sphere(r=0.01);
        }
    }

    difference() {
        difference() {
            model();
            minkowski() {
                scale([0.9866668891869602, 0.9741968775809327, 0.9833333333333334])
                    model();
                sphere(r=0.01);
            }
        }
        translate([0, 0, -0.001])
            cube([60.10100135803223, 31.10399971008301, 0.002], center=true);
    }
    