import pandas as pd
import glob
import os

print("--- Inspecting hardwareStore.csv ---")
df_inventory = pd.read_csv("Inventory/hardwareStore.csv")
print("Columns:", df_inventory.columns.tolist())
print("Shape:", df_inventory.shape)
print("Unique Categories:", df_inventory["CATEGORY_NAME"].unique() if "CATEGORY_NAME" in df_inventory.columns else "N/A")
print("Sample Product Names:", df_inventory["PRODUCT_NAME"].head(10).tolist())
print()

print("--- Inspecting Vendor_RFQ_Database.csv ---")
df_rfq = pd.read_csv("Vendor_RFQ_Database/Vendor_RFQ_Database.csv")
print("Columns:", df_rfq.columns.tolist())
print("Shape:", df_rfq.shape)
print("Unique Vendors:", df_rfq["Vendor_Name"].unique() if "Vendor_Name" in df_rfq.columns else "N/A")
print("Unique Items:", df_rfq["Item_Name"].unique() if "Item_Name" in df_rfq.columns else "N/A")
print()

print("--- Inspecting laptop.csv ---")
df_laptop = pd.read_csv("Laptop Dataset/laptop.csv")
print("Columns:", df_laptop.columns.tolist())
print("Shape:", df_laptop.shape)
print("Unique Brands:", df_laptop["Brand"].unique() if "Brand" in df_laptop.columns else "N/A")
print("Sample Names:", df_laptop["Name"].head(3).tolist())
print()

print("--- Inspecting Procurement KPI Analysis Dataset.csv ---")
df_kpi = pd.read_csv("RFQPurchase Orders/Procurement KPI Analysis Dataset.csv")
print("Columns:", df_kpi.columns.tolist())
print("Shape:", df_kpi.shape)
print("Unique Suppliers:", df_kpi["Supplier"].unique() if "Supplier" in df_kpi.columns else "N/A")
print("Unique Item Categories:", df_kpi["Item_Category"].unique() if "Item_Category" in df_kpi.columns else "N/A")
print()
