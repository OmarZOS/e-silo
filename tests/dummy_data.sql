-- ==================== PRODUCT DUMMY DATA ====================
-- All reserved quantities are 0

INSERT INTO `gluttex`.`product` (
    `id_product`,
    `product_name`,
    `product_brand`,
    `product_barcode`,
    `product_description`,
    `product_price`,
    `product_base_price`,
    `product_quantity`,
    `product_reserved_quantity`,
    `product_quantifier`,
    `product_visibility`
) VALUES
-- Medical Supplies
(1, 'Surgical Mask Level 3', 'MediSafe', 'MS-001-2024', 'High-quality surgical masks for medical use', 15.99, 12.50, 5000, 0, 'pack', 'VISIBLE'),
(2, 'Nitrile Gloves - Large', 'SafeHands', 'SH-002-2024', 'Powder-free nitrile examination gloves', 25.50, 22.00, 3000, 0, 'box', 'VISIBLE'),
(3, 'Medical Syringe 5ml', 'PrecisionMed', 'PM-003-2024', 'Sterile medical syringes with needle', 0.75, 0.50, 10000, 0, 'each', 'VISIBLE'),
(4, 'Isopropyl Alcohol 70%', 'PureClean', 'PC-004-2024', 'Antiseptic alcohol solution', 8.99, 7.50, 2000, 0, 'bottle', 'VISIBLE'),
(5, 'Bandage Assortment', 'HealFast', 'HF-005-2024', 'Mixed sizes of adhesive bandages', 12.99, 10.00, 1500, 0, 'set', 'VISIBLE'),
(6, 'COVID-19 Rapid Test Kit', 'TestSure', 'TS-006-2024', '15-minute rapid antigen test', 8.50, 6.00, 500, 0, 'each', 'VISIBLE'),
(7, 'Thermometer Digital', 'TempGuard', 'TG-007-2024', 'Digital medical thermometer', 19.99, 15.00, 200, 0, 'each', 'VISIBLE'),
(8, 'IV Drip Set', 'InfusionPro', 'IP-008-2024', 'Sterile IV administration set', 4.50, 3.50, 800, 0, 'each', 'VISIBLE'),
(9, 'Blood Glucose Monitor', 'GlucoCheck', 'GC-009-2024', 'Digital blood glucose monitoring system', 34.99, 28.00, 150, 0, 'each', 'VISIBLE'),
(10, 'Vitamin C Supplement', 'NutriVita', 'NV-010-2024', '100mg Vitamin C tablets', 14.99, 12.00, 1000, 0, 'bottle', 'VISIBLE'),

-- Pharmaceutical Products
(11, 'Paracetamol 500mg', 'PharmaPlus', 'PP-011-2024', 'Pain reliever and fever reducer', 5.99, 4.50, 2000, 0, 'box', 'VISIBLE'),
(12, 'Amoxicillin 250mg', 'PharmaPlus', 'PP-012-2024', 'Antibiotic for bacterial infections', 12.50, 10.00, 800, 0, 'box', 'VISIBLE'),
(13, 'Cetirizine 10mg', 'AllergyCare', 'AC-013-2024', 'Antihistamine for allergies', 8.99, 7.00, 1200, 0, 'box', 'VISIBLE'),
(14, 'Omeprazole 20mg', 'GastroMed', 'GM-014-2024', 'Acid reducer for heartburn', 15.50, 12.50, 600, 0, 'box', 'VISIBLE'),
(15, 'Lisinopril 10mg', 'CardioCare', 'CC-015-2024', 'Blood pressure medication', 18.99, 15.00, 500, 0, 'box', 'VISIBLE'),
(16, 'Metformin 500mg', 'DiabetoMed', 'DM-016-2024', 'Diabetes medication', 9.99, 8.00, 700, 0, 'box', 'VISIBLE'),
(17, 'Ibuprofen 400mg', 'PharmaPlus', 'PP-017-2024', 'Anti-inflammatory pain reliever', 7.99, 6.00, 1500, 0, 'box', 'VISIBLE'),
(18, 'Multivitamin Complex', 'NutriVita', 'NV-018-2024', 'Complete daily multivitamin', 22.50, 18.00, 400, 0, 'bottle', 'VISIBLE'),
(19, 'Antibiotic Cream', 'HealFast', 'HF-019-2024', 'Topical antibiotic ointment', 6.99, 5.50, 300, 0, 'tube', 'VISIBLE'),
(20, 'Inhaler - 200 doses', 'BreatheWell', 'BW-020-2024', 'Bronchodilator inhaler', 35.00, 28.00, 200, 0, 'each', 'VISIBLE'),

-- Lab Equipment & Supplies
(21, 'Microscope Slide Set', 'LabTech', 'LT-021-2024', 'Box of 100 microscope slides', 18.50, 15.00, 300, 0, 'box', 'VISIBLE'),
(22, 'Petri Dish 90mm', 'BioLab', 'BL-022-2024', 'Sterile petri dishes', 12.99, 10.50, 500, 0, 'pack', 'VISIBLE'),
(23, 'Laboratory Centrifuge', 'LabTech', 'LT-023-2024', 'Benchtop centrifuge, 12-place', 450.00, 400.00, 5, 0, 'each', 'VISIBLE'),
(24, 'PCR Test Kit', 'GenoTest', 'GT-024-2024', 'PCR testing kit for 100 samples', 299.99, 250.00, 15, 0, 'each', 'VISIBLE'),
(25, 'Microscope Eyepiece', 'OptiClear', 'OC-025-2024', '10x microscope eyepiece', 89.99, 75.00, 8, 0, 'each', 'VISIBLE'),

-- Hospital Equipment
(26, 'Hospital Bed - Adjustable', 'CareMed', 'CM-026-2024', 'Electric hospital bed with side rails', 1250.00, 1100.00, 10, 0, 'each', 'VISIBLE'),
(27, 'IV Stand', 'CareMed', 'CM-027-2024', 'Stainless steel IV infusion stand', 85.00, 70.00, 30, 0, 'each', 'VISIBLE'),
(28, 'Heart Monitor', 'CardioTech', 'CT-028-2024', '3-channel ECG monitor', 2450.00, 2200.00, 6, 0, 'each', 'VISIBLE'),
(29, 'Oxygen Concentrator', 'OxyFlow', 'OF-029-2024', '5L/min oxygen concentrator', 550.00, 475.00, 12, 0, 'each', 'VISIBLE'),
(30, 'Wheelchair - Standard', 'MobilityPlus', 'MP-030-2024', 'Standard adult wheelchair', 320.00, 275.00, 15, 0, 'each', 'VISIBLE'),

-- Emergency Supplies
(31, 'First Aid Kit - Complete', 'RescueMed', 'RM-031-2024', 'Complete first aid kit for emergencies', 45.99, 38.00, 50, 0, 'kit', 'VISIBLE'),
(32, 'CPR Mask - Pocket', 'RescueMed', 'RM-032-2024', 'Pocket CPR mask with valve', 12.50, 9.99, 200, 0, 'each', 'VISIBLE'),
(33, 'Tourniquet - Emergency', 'TraumaCare', 'TC-033-2024', 'Combat application tourniquet', 24.99, 20.00, 100, 0, 'each', 'VISIBLE'),
(34, 'Burn Dressing Kit', 'HealFast', 'HF-034-2024', 'Specialized burn wound kit', 18.99, 15.00, 75, 0, 'kit', 'VISIBLE'),
(35, 'Cold Pack - Instant', 'RescueMed', 'RM-035-2024', 'Instant chemical cold pack', 3.99, 3.00, 500, 0, 'each', 'VISIBLE'),

-- Medical Equipment
(36, 'Stethoscope - Professional', 'CardioLab', 'CL-036-2024', 'Professional acoustic stethoscope', 89.99, 75.00, 40, 0, 'each', 'VISIBLE'),
(37, 'Blood Pressure Monitor', 'PressureCheck', 'PC-037-2024', 'Digital upper arm BP monitor', 49.99, 40.00, 60, 0, 'each', 'VISIBLE'),
(38, 'Pulse Oximeter', 'OxyCheck', 'OC-038-2024', 'Finger pulse oximeter with display', 29.99, 24.99, 100, 0, 'each', 'VISIBLE'),
(39, 'Surgical Scissors', 'SurgiCare', 'SC-039-2024', 'Stainless steel surgical scissors', 15.99, 12.99, 80, 0, 'each', 'VISIBLE'),
(40, 'Medical Tray - Stainless', 'CareMed', 'CM-040-2024', 'Stainless steel medical instrument tray', 45.00, 38.00, 25, 0, 'each', 'VISIBLE');


-- ==================== ORDERED ITEM DUMMY DATA ====================
-- All reserved_quantity is 0

INSERT INTO `gluttex`.`ordered_item` (
    `id_ordered_item`,
    `ordered_product_id`,
    `ordered_quantity`,
    `reserved_quantity`,
    `applied_vat`,
    `unit_price`,
    `product_discount`,
    `ordered_item_delivery_status`,
    `ordered_item_delivery_fee`
) VALUES
-- Batch 1 - Medical Supplies (Products 1-10)
(1, 1, 100, 0, 19.00, 15.99, 0.00, 'delivered', 0.00),
(2, 2, 50, 0, 19.00, 25.50, 5.00, 'delivered', 0.00),
(3, 3, 200, 0, 19.00, 0.75, 0.00, 'delivered', 0.00),
(4, 4, 30, 0, 19.00, 8.99, 0.00, 'shipped', 5.99),
(5, 5, 25, 0, 19.00, 12.99, 2.00, 'shipped', 5.99),
(6, 6, 15, 0, 19.00, 8.50, 0.00, 'shipped', 5.99),

-- Batch 2 - Pharmaceuticals (Products 11-20)
(7, 11, 30, 0, 15.00, 5.99, 0.00, 'delivered', 0.00),
(8, 12, 20, 0, 15.00, 12.50, 2.50, 'delivered', 0.00),
(9, 13, 25, 0, 15.00, 8.99, 0.00, 'delivered', 0.00),
(10, 14, 10, 0, 15.00, 15.50, 0.00, 'shipped', 0.00),
(11, 15, 8, 0, 15.00, 18.99, 3.00, 'shipped', 0.00),
(12, 16, 15, 0, 15.00, 9.99, 0.00, 'shipped', 0.00),
(13, 17, 40, 0, 15.00, 7.99, 0.00, 'delivered', 0.00),
(14, 18, 5, 0, 15.00, 22.50, 2.50, 'delivered', 0.00),
(15, 19, 12, 0, 15.00, 6.99, 0.00, 'shipped', 0.00),
(16, 20, 3, 0, 15.00, 35.00, 5.00, 'shipped', 0.00),

-- Batch 3 - Lab Equipment (Products 21-25)
(17, 21, 10, 0, 0.00, 18.50, 0.00, 'delivered', 0.00),
(18, 22, 20, 0, 0.00, 12.99, 0.00, 'delivered', 0.00),
(19, 23, 1, 0, 0.00, 450.00, 0.00, 'delivered', 0.00),
(20, 24, 2, 0, 0.00, 299.99, 50.00, 'processing', 0.00),
(21, 25, 1, 0, 0.00, 89.99, 0.00, 'processing', 0.00),

-- Batch 4 - Hospital Equipment (Products 26-30)
(22, 26, 2, 0, 19.00, 1250.00, 0.00, 'processing', 50.00),
(23, 27, 5, 0, 19.00, 85.00, 0.00, 'processing', 50.00),
(24, 28, 1, 0, 19.00, 2450.00, 0.00, 'pending', 50.00),
(25, 29, 2, 0, 19.00, 550.00, 25.00, 'pending', 50.00),
(26, 30, 3, 0, 19.00, 320.00, 0.00, 'pending', 50.00),

-- Batch 5 - Emergency Supplies (Products 31-35)
(27, 31, 5, 0, 0.00, 45.99, 0.00, 'pending', 0.00),
(28, 32, 15, 0, 0.00, 12.50, 0.00, 'pending', 0.00),
(29, 33, 8, 0, 0.00, 24.99, 0.00, 'pending', 0.00),
(30, 34, 10, 0, 0.00, 18.99, 0.00, 'pending', 0.00),
(31, 35, 50, 0, 0.00, 3.99, 0.00, 'pending', 0.00),

-- Batch 6 - Medical Equipment (Products 36-40)
(32, 36, 3, 0, 0.00, 89.99, 10.00, 'pending', 0.00),
(33, 37, 5, 0, 0.00, 49.99, 0.00, 'pending', 0.00),
(34, 38, 10, 0, 0.00, 29.99, 0.00, 'pending', 0.00),
(35, 39, 8, 0, 0.00, 15.99, 0.00, 'pending', 0.00),
(36, 40, 4, 0, 0.00, 45.00, 0.00, 'pending', 0.00);


-- ==================== PRODUCT CONSUMPTION DUMMY DATA ====================
-- All product_reserved_quantity is 0

INSERT INTO `gluttex`.`product_consumption` (
    `id_product_consumption`,
    `consumed_product_id`,
    `product_reserved_quantity`
) VALUES
-- Service 1 - General Checkup (consumes various medical supplies)
(1, 1, 0),  -- Surgical Masks
(2, 2, 0),  -- Nitrile Gloves
(3, 4, 0),  -- Isopropyl Alcohol
(4, 5, 0),  -- Bandages

-- Service 2 - COVID-19 Testing
(5, 6, 0),  -- Rapid Test Kits
(6, 1, 0),  -- Surgical Masks
(7, 2, 0),  -- Nitrile Gloves

-- Service 3 - Blood Test
(8, 3, 0),  -- Medical Syringes
(9, 4, 0),  -- Isopropyl Alcohol
(10, 9, 0), -- Blood Glucose Monitor
(11, 21, 0),-- Microscope Slides

-- Service 4 - Vaccination
(12, 3, 0),  -- Medical Syringes
(13, 4, 0),  -- Isopropyl Alcohol
(14, 2, 0),  -- Nitrile Gloves
(15, 11, 0), -- Paracetamol (for post-vaccination)

-- Service 5 - Minor Surgery
(16, 1, 0),  -- Surgical Masks
(17, 2, 0),  -- Nitrile Gloves
(18, 3, 0),  -- Medical Syringes
(19, 4, 0), -- Isopropyl Alcohol
(20, 8, 0), -- IV Drip Set
(21, 39, 0),-- Surgical Scissors

-- Service 6 - Dental Checkup
(22, 1, 0),  -- Surgical Masks
(23, 2, 0),  -- Nitrile Gloves
(24, 4, 0),  -- Isopropyl Alcohol
(25, 5, 0),  -- Bandages

-- Service 7 - Laboratory Test
(26, 21, 0), -- Microscope Slides
(27, 22, 0), -- Petri Dishes
(28, 24, 0), -- PCR Test Kit
(29, 3, 0),  -- Medical Syringes

-- Service 8 - Emergency Treatment
(30, 31, 0), -- First Aid Kit
(31, 32, 0), -- CPR Mask
(32, 33, 0), -- Tourniquet
(33, 34, 0), -- Burn Dressing
(34, 35, 0), -- Cold Pack

-- Service 9 - Equipment Setup
(35, 26, 0), -- Hospital Bed
(36, 27, 0), -- IV Stand
(37, 29, 0), -- Oxygen Concentrator

-- Service 10 - Monitoring
(38, 28, 0), -- Heart Monitor
(39, 37, 0), -- Blood Pressure Monitor
(40, 38, 0), -- Pulse Oximeter
(41, 7, 0),  -- Digital Thermometer

-- Service 11 - Wound Care
(42, 4, 0),  -- Isopropyl Alcohol
(43, 19, 0), -- Antibiotic Cream
(44, 5, 0),  -- Bandages
(45, 2, 0),  -- Nitrile Gloves

-- Service 12 - Nutrition Consultation
(46, 10, 0), -- Vitamin C Supplement
(47, 18, 0); -- Multivitamin Complex