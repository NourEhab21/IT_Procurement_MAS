import os
import re
import time
import json
import pandas as pd
from typing import Dict, List, Tuple, Any

# ==========================================
# 1. DATABASE LOADER & PATH RESOLVER
# ==========================================

def locate_file(filename: str) -> str:
    """
    Locates files by checking the current directory, Colab's /content folder,
    or specific allowed subfolders (Inventory, Laptop Dataset, Vendor_RFQ_Database).
    Explicitly avoids scanning VendorSupplier and RFQPurchase Orders.
    """
    target_name = filename
    if filename == "hardwareStore.csv":
        target_name = "Laptop_Inventory_Database.csv"

    # 1. Direct match in current directory
    if os.path.exists(target_name):
        return target_name
    if os.path.exists(filename):
        return filename

    # 2. Check Colab default upload path
    colab_path = os.path.join('/content', target_name)
    if os.path.exists(colab_path):
        return colab_path
    colab_orig = os.path.join('/content', filename)
    if os.path.exists(colab_orig):
        return colab_orig
    
    # 3. Check allowed subdirectories (excluding VendorSupplier and RFQPurchase Orders)
    allowed_dirs = ['Inventory', 'Vendor_RFQ_Database', 'Laptop Dataset']
    for d in allowed_dirs:
        path = os.path.join(d, target_name)
        if os.path.exists(path):
            return path
        path_orig = os.path.join(d, filename)
        if os.path.exists(path_orig):
            return path_orig
        
        if os.path.exists(d):
            for f in os.listdir(d):
                norm_f = f.lower().replace('_', '').replace(' ', '')
                norm_target = target_name.lower().replace('_', '').replace(' ', '')
                if norm_f == norm_target or norm_f.replace('.csv', '') == norm_target.replace('.csv', ''):
                    return os.path.join(d, f)
            if "inventory" in target_name.lower() or "laptop" in target_name.lower():
                csv_files = [f for f in os.listdir(d) if f.endswith('.csv')]
                if csv_files:
                    return os.path.join(d, csv_files[0])
                
    return target_name

def load_databases() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads only the 3 required databases into pandas DataFrames:
    1. Laptop_Inventory_Database.csv (Inventory DB)
    2. Vendor_RFQ_Database.csv (Vendor & RFQ DB)
    3. laptop.csv (IT Specifications DB)
    """
    print("\n" + "="*50)
    print("LOADING DATABASES (3 Files)...")
    print("="*50)
    
    inventory_path = locate_file("Laptop_Inventory_Database.csv")
    rfq_path = locate_file("Vendor_RFQ_Database.csv")
    laptop_path = locate_file("laptop.csv")
    
    print(f"1. Inventory DB resolved to: {inventory_path}")
    print(f"2. Vendor RFQ DB resolved to: {rfq_path}")
    print(f"3. Laptop Specs DB resolved to: {laptop_path}")
    
    df_inventory = pd.read_csv(inventory_path)
    df_rfq = pd.read_csv(rfq_path)
    df_laptop = pd.read_csv(laptop_path)
    
    print(f"-> Inventory DB loaded successfully: {df_inventory.shape[0]} rows")
    print(f"-> Vendor RFQ DB loaded successfully: {df_rfq.shape[0]} rows")
    print(f"-> Laptop Specs DB loaded successfully: {df_laptop.shape[0]} rows")
    print("="*50 + "\n")
    
    return df_inventory, df_rfq, df_laptop

# ==========================================
# 2. DATA PROCESSING INTERFACES
# ==========================================

def query_inventory(
    item_name: str,
    category: str,
    df_inventory: pd.DataFrame,
    requested_qty: Any = 1,
    request_text: str = ""
) -> Tuple[str, str, int, str]:
    """
    Checks Laptop_Inventory_Database.csv for stock using strict BRAND and PRODUCT_NAME matching.
    - First matches BRAND column exactly.
    - Then matches PRODUCT_NAME for specific product type (Gaming vs Business vs Standard).
    - NEVER matches different brands or uses broad keyword fallbacks.
    - If brand or product type does not match -> returns NOT_FOUND immediately.
    """
    try:
        requested_qty = int(requested_qty)
    except Exception:
        requested_qty = 1
    if requested_qty <= 0:
        requested_qty = 1

    clean_cat_input = re.sub(r'[^\w\s]', '', category).strip().lower()
    cat_column = 'CATEGORY_NAME' if 'CATEGORY_NAME' in df_inventory.columns else df_inventory.columns[1]
    inventory_categories = [str(cat).strip().lower() for cat in df_inventory[cat_column].unique()]
    
    category_exists = any(inv_cat in clean_cat_input or clean_cat_input in inv_cat for inv_cat in inventory_categories)
    if not category_exists:
        available_cats = ", ".join([str(c) for c in df_inventory[cat_column].unique()])
        return "NOT_FOUND", f"Requested category '{category}' does not exist in inventory database (Available categories: {available_cats}).", 0, ""

    brand_col = 'BRAND' if 'BRAND' in df_inventory.columns else df_inventory.columns[2]
    prod_col = 'PRODUCT_NAME' if 'PRODUCT_NAME' in df_inventory.columns else df_inventory.columns[3]
    qty_col = 'QUANTITY' if 'QUANTITY' in df_inventory.columns else 'QUANTITY'
    wh_col = 'WAREHOUSE_NAME' if 'WAREHOUSE_NAME' in df_inventory.columns else 'WAREHOUSE_NAME'
    
    df_inventory_copy = df_inventory.copy()
    df_inventory_copy[qty_col] = pd.to_numeric(df_inventory_copy[qty_col], errors='coerce').fillna(0).astype(int)
    
    in_stock = df_inventory_copy[df_inventory_copy[qty_col] > 0].copy()
    if in_stock.empty:
        return "NOT_FOUND", "Item is out of stock in existing inventory database.", 0, ""

    search_text = f"{item_name} {request_text}".lower()

    # 1. STRICT BRAND MATCH: Extract requested brand and match BRAND column exactly
    known_brands = ['dell', 'hp', 'lenovo', 'apple', 'acer', 'asus', 'msi', 'infinix', 'tecno', 'microsoft']
    requested_brand = ""
    for b in known_brands:
        if re.search(r'\b' + re.escape(b) + r'\b', search_text):
            requested_brand = b
            break

    if requested_brand:
        brand_stock = in_stock[in_stock[brand_col].astype(str).str.lower() == requested_brand]
        if brand_stock.empty:
            return "NOT_FOUND", f"No inventory stock found for requested brand '{requested_brand.upper()}'.", 0, ""
    else:
        brand_stock = in_stock

    # 2. STRICT PRODUCT TYPE MATCH: Check PRODUCT_NAME for product type qualifiers (Gaming vs Business vs Standard)
    product_types = {'gaming', 'business', 'workstation', 'chromebook', 'macbook', 'air', 'pro', 'studio', 'slim', 'touch', 'convertible'}
    requested_types = {pt for pt in product_types if re.search(r'\b' + pt + r'\b', search_text)}

    if requested_types:
        matched_rows = brand_stock[brand_stock[prod_col].astype(str).str.lower().apply(lambda name: all(pt in name for pt in requested_types))]
    else:
        # Standard product request (e.g. "HP Laptop") -> exclude specialized types like 'business' or 'gaming'
        candidate_types = {'gaming', 'business', 'workstation', 'chromebook', 'macbook', 'pro', 'studio', 'slim', 'touch'}
        matched_rows = brand_stock[~brand_stock[prod_col].astype(str).str.lower().apply(lambda name: any(pt in name for pt in candidate_types))]
        if matched_rows.empty:
            matched_rows = brand_stock

    if matched_rows.empty:
        return "NOT_FOUND", f"No exact product type matched your request in inventory for brand '{requested_brand.upper()}'.", 0, ""

    # Select exact matched product name and calculate stock
    first_product_name = matched_rows[prod_col].iloc[0]
    product_group = matched_rows[matched_rows[prod_col] == first_product_name]
    available_qty = int(product_group[qty_col].sum())

    details = []
    for _, row in product_group.iterrows():
        details.append(f"- {row[prod_col]} ({row[wh_col]}): {int(row[qty_col])} unit(s)")
    details_str = "\n".join(details)

    if available_qty >= requested_qty:
        status = "FULL"
        msg = f"FULL stock available! Found {available_qty} unit(s) of '{first_product_name}' in inventory (Requested: {requested_qty}).\nLocations:\n{details_str}"
    elif available_qty > 0:
        status = "PARTIAL"
        msg = f"PARTIAL stock available! Found {available_qty} unit(s) of '{first_product_name}' in inventory (Requested: {requested_qty}).\nCollect {available_qty} unit(s) from warehouse; remaining {requested_qty - available_qty} unit(s) passed to Orchestrator for procurement.\nLocations:\n{details_str}"
    else:
        status = "NOT_FOUND"
        msg = f"Product '{first_product_name}' was found in catalog but is currently out of stock."

    return status, msg, available_qty, str(first_product_name)

def query_vendors(item_category: str, df_rfq: pd.DataFrame, requested_brand: str = "") -> Tuple[str, bool, bool]:
    """
    Finds vendors from Vendor_RFQ_Database.csv.
    Filters strictly for requested_brand if specified and found in DB.
    Returns (table_markdown, has_incomplete_specs, brand_found).
    """
    clean_cat = re.sub(r'[^\w\s]', '', item_category).strip().lower()
    clean_brand = re.sub(r'[^\w\s]', '', requested_brand).strip().lower() if requested_brand else ""
    
    category_matches = df_rfq[df_rfq['Item_Category'].astype(str).str.lower().str.contains(clean_cat, regex=False, na=False)].copy()
    if category_matches.empty:
        category_matches = df_rfq[df_rfq['Item_Name'].astype(str).str.lower().str.contains(clean_cat, regex=False, na=False)].copy()
        
    if category_matches.empty:
        category_matches = df_rfq.copy()
        
    brand_found = False
    if clean_brand:
        brand_matches = category_matches[
            category_matches['Item_Name'].astype(str).str.lower().str.contains(clean_brand, regex=False, na=False) |
            category_matches['Vendor_Name'].astype(str).str.lower().str.contains(clean_brand, regex=False, na=False)
        ]
        if not brand_matches.empty:
            category_matches = brand_matches
            brand_found = True
            
    cols = ['Vendor_Name', 'Item_Name', 'Unit_Price_USD', 'Delivery_Days', 'Warranty_Years', 'Vendor_Rating', 'Order_Accuracy_Pct']
    existing_cols = [c for c in cols if c in df_rfq.columns]
    
    result_table = category_matches[existing_cols].to_markdown(index=False)
    
    has_incomplete_specs = True
    
    filter_note = ""
    if clean_brand and brand_found:
        filter_note = f"\n\n[DATABASE FILTER: Displaying ONLY vendors for requested brand '{requested_brand.upper()}'.]"
    elif clean_brand and not brand_found:
        filter_note = f"\n\n[DATABASE FILTER: Requested brand '{requested_brand.upper()}' has no direct vendor bids in DB. Displaying all available category vendors.]"

    return result_table + filter_note, has_incomplete_specs, brand_found

def query_laptop_specs(brand: str, df_laptop: pd.DataFrame) -> str:
    """
    Queries laptop.csv for laptop specifications of a specific brand.
    """
    clean_brand = re.sub(r'[^\w\s]', '', brand).strip().lower()
    
    matches = df_laptop[df_laptop['Brand'].astype(str).str.lower() == clean_brand]
    if matches.empty:
        matches = df_laptop[df_laptop['Name'].astype(str).str.lower().str.contains(clean_brand, regex=False, na=False)]
        
    if matches.empty:
        return f"No laptops found in laptop.csv database for brand: '{brand}'."
        
    matches_sorted = matches.sort_values(by='Price')
    step = max(1, len(matches_sorted) // 8)
    subset = matches_sorted.iloc[::step].head(8)
    
    cols = ['Brand', 'Name', 'Price', 'Processor_Name', 'RAM', 'SSD', 'HDD', 'Display']
    existing_cols = [c for c in cols if c in df_laptop.columns]
    
    result = f"Laptop specifications for {brand.upper()} models in database:\n"
    result += subset[existing_cols].to_markdown(index=False)
    return result

def calculate_finance_scores(df_rfq: pd.DataFrame, category: str = "Laptop") -> str:
    """
    Reads directly from Vendor_RFQ_Database.csv and scores each vendor on a 0-100 scale.
    """
    clean_cat = re.sub(r'[^\w\s]', '', category).strip().lower()
    matches = df_rfq[df_rfq['Item_Category'].astype(str).str.lower() == clean_cat].copy()
    if matches.empty:
        matches = df_rfq[df_rfq['Item_Name'].astype(str).str.lower().str.contains(clean_cat, regex=False, na=False)].copy()
        
    if matches.empty:
        return "No vendors matched category/name in Vendor_RFQ_Database.csv to score."
        
    min_price = matches['Unit_Price_USD'].min()
    min_delivery = matches['Delivery_Days'].min()
    max_warranty = matches['Warranty_Years'].max()
    
    scores = []
    for _, row in matches.iterrows():
        price = row['Unit_Price_USD']
        delivery = row['Delivery_Days']
        warranty = row['Warranty_Years']
        rating = row['Vendor_Rating']
        accuracy = row['Order_Accuracy_Pct']
        
        p_score = 20 * (min_price / price) if price > 0 else 0
        d_score = 20 * (min_delivery / delivery) if delivery > 0 else 0
        w_score = 20 * (warranty / max_warranty) if max_warranty > 0 else 0
        r_score = 20 * (rating / 5.0)
        a_score = 20 * (accuracy / 100.0)
        
        total_score = round(p_score + d_score + w_score + r_score + a_score, 2)
        
        scores.append({
            'Vendor_Name': row['Vendor_Name'],
            'Item_Name': row['Item_Name'],
            'Unit_Price_USD': price,
            'Delivery_Days': delivery,
            'Warranty_Years': warranty,
            'Vendor_Rating': rating,
            'Order_Accuracy_Pct': accuracy,
            'Price_Score': round(p_score, 1),
            'Delivery_Score': round(d_score, 1),
            'Warranty_Score': round(w_score, 1),
            'Rating_Score': round(r_score, 1),
            'Accuracy_Score': round(a_score, 1),
            'Total_Score': total_score
        })
        
    df_scores = pd.DataFrame(scores)
    df_scores = df_scores.sort_values(by='Total_Score', ascending=False)
    return df_scores.to_markdown(index=False)

# ==========================================
# 3. BASE AGENT LOGIC & CLIENT SETUP
# ==========================================

class ConversationLogger:
    """
    Utility class to log and print step-by-step agent actions with nice formatting.
    """
    @staticmethod
    def log_agent_start(agent_name: str):
        print("\n" + "="*60)
        print(f"🤖 AGENT ACTIVATED: {agent_name.upper()}")
        print("="*60)
        
    @staticmethod
    def log_agent_action(action: str):
        print(f"🔍 Action: {action}")
        
    @staticmethod
    def log_agent_output(agent_name: str, output: str):
        print(f"\n📥 {agent_name} Response:")
        print("-" * 40)
        print(output)
        print("-" * 40)

def parse_proxy_output(proxy_response: str, request_text: str) -> Tuple[str, str, str, int, int]:
    """
    Safely parses Proxy Agent output for REWRITTEN_REQUEST, CATEGORY, SEARCH_KEYWORDS, QUANTITY, and BUDGET.
    Applies robust regex extraction with fallbacks and comma stripping.
    """
    rewritten_req = request_text
    category = "Laptop"
    search_term = request_text
    quantity = 1
    budget = 5000

    try:
        req_match = re.search(r"REWRITTEN_REQUEST:\s*(.*)", proxy_response, re.IGNORECASE)
        if req_match:
            rewritten_req = req_match.group(1).strip()
    except Exception:
        rewritten_req = request_text

    try:
        cat_match = re.search(r"CATEGORY:\s*(.*)", proxy_response, re.IGNORECASE)
        if cat_match:
            raw_cat = cat_match.group(1).strip()
            category = re.sub(r'[^\w\s]', '', raw_cat).strip()
            if not category: category = "Laptop"
    except Exception:
        category = "Laptop"

    try:
        key_match = re.search(r"SEARCH_KEYWORDS:\s*(.*)", proxy_response, re.IGNORECASE)
        if key_match:
            raw_keys = key_match.group(1).strip()
            search_term = re.sub(r'[^\w\s]', ' ', raw_keys).strip()
            if not search_term: search_term = request_text
    except Exception:
        search_term = re.sub(r'[^\w\s]', ' ', request_text).strip()

    try:
        qty_match = re.search(r"QUANTITY:\s*(\d+)", proxy_response, re.IGNORECASE)
        if qty_match:
            quantity = int(qty_match.group(1).strip())
        else:
            num_match = re.search(r"(\d+)\s*(?:x|units?|laptops?|pcs?|items?)", request_text, re.IGNORECASE)
            if num_match:
                quantity = int(num_match.group(1).strip())
    except Exception:
        quantity = 1

    try:
        quantity = int(quantity)
    except Exception:
        quantity = 1
    if quantity <= 0:
        quantity = 1

    try:
        budget_match = re.search(r"BUDGET:\s*\$?([\d,]+)", proxy_response, re.IGNORECASE)
        if budget_match:
            raw_b = budget_match.group(1).replace(',', '').strip()
            budget = int(raw_b)
        else:
            req_budget = re.search(r"(?:budget|cost)\s*(?:is|=|:|\$)?\s*\$?([\d,]+)", request_text, re.IGNORECASE)
            if req_budget:
                raw_b = req_budget.group(1).replace(',', '').strip()
                budget = int(raw_b)
    except Exception:
        budget = 5000

    try:
        budget = int(budget)
    except Exception:
        budget = 5000
    if budget <= 0:
        budget = 5000

    return rewritten_req, category, search_term, quantity, budget

# ==========================================
# VERSION 1: ANTHROPIC CLAUDE WORKFLOW
# ==========================================

def run_workflow_claude(
    request_text: str,
    df_inventory: pd.DataFrame,
    df_rfq: pd.DataFrame,
    df_laptop: pd.DataFrame,
    anthropic_client,
    model_name: str = "claude-sonnet-4-6"
) -> Tuple[List[Dict[str, str]], str]:
    """
    Executes the 13-step IT procurement workflow using ONLY Anthropic Claude.
    """
    history = []
    
    def call_claude(system_prompt: str, user_prompt: str) -> str:
        message = anthropic_client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return message.content[0].text

    # ----------------------------------------------------
    # STEP 1 - Human opens ticket
    # ----------------------------------------------------
    print(f"\n[STEP 1 - Human opens ticket]\nRequest: {request_text}\n")
    history.append({"role": "Human", "agent": "Human", "content": request_text})
    
    # ----------------------------------------------------
    # STEP 2 - Proxy Agent
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("Proxy Agent")
    proxy_system = (
        "You are the Proxy Agent. Read the human's IT procurement request and output a short, simple summary.\n"
        "DO NOT use markdown formatting, tables, bold headers, bullet points, or emojis.\n"
        "Your output MUST strictly follow this exact 5-line format:\n\n"
        "REWRITTEN_REQUEST: <short 1-line clear description of requested item and specs>\n"
        "CATEGORY: <item category e.g. Laptop>\n"
        "SEARCH_KEYWORDS: <space separated keywords with letters and numbers only>\n"
        "QUANTITY: <integer quantity requested>\n"
        "BUDGET: <integer budget in USD extracted from user request, e.g. 1000. If no budget mentioned, output 5000>"
    )
    proxy_response = call_claude(proxy_system, f"Human Request: {request_text}")
    ConversationLogger.log_agent_output("Proxy Agent", proxy_response)
    history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": proxy_response})
    
    rewritten_req, category, search_term, quantity, stated_budget = parse_proxy_output(proxy_response, request_text)
    
    ConversationLogger.log_agent_action("Checking Laptop_Inventory_Database.csv...")
    inv_status, inv_msg, available_qty, matched_product = query_inventory(search_term, category, df_inventory, quantity, request_text)
    print(f"Inventory Search Results [{inv_status}]:\n{inv_msg}\n")
    
    if inv_status == "FULL":
        close_msg = f"TICKET CLOSED: All {quantity} unit(s) of '{matched_product}' exist in stock. Please proceed to warehouse."
        print(close_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": close_msg})
        return history, "Closed - Item in Inventory"
    elif inv_status == "PARTIAL":
        needed_qty = quantity - available_qty
        partial_msg = f"PARTIAL INVENTORY: {available_qty} unit(s) of '{matched_product}' available in warehouse. Routing remaining {needed_qty} unit(s) to Orchestrator Agent for procurement."
        print(partial_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": partial_msg})
        current_request = f"{rewritten_req} (Quantity Required: {needed_qty} units, User Budget: ${stated_budget})"
    else:
        notFound_msg = f"NOT IN INVENTORY: Item not available in stock. Passing full request for {quantity} unit(s) to Orchestrator Agent."
        print(notFound_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": notFound_msg})
        current_request = f"{rewritten_req} (Quantity Required: {quantity} units, User Budget: ${stated_budget})"
    
    rfq_output = ""
    it_output = ""
    finance_output = ""
    
    # ----------------------------------------------------
    # STEP 3 - Orchestrator Agent routes to RFQ Agent
    # ----------------------------------------------------
    orchestrator_system = (
        "You are the Orchestrator Agent. Route requests and validate agent reports.\n"
        "When validating, respond ONLY in structured JSON format: {\"valid\": true/false, \"feedback\": \"description\"}"
    )
    
    rfq_attempts = 0
    rfq_valid = False
    rfq_feedback = "Please retrieve the top vendors matching requested brand from Vendor_RFQ_Database.csv."
    
    text_to_scan = f"{request_text} {current_request}".lower()
    known_brands = ['dell', 'hp', 'lenovo', 'apple', 'acer', 'asus', 'msi', 'infinix', 'tecno', 'microsoft']
    detected_brand = ""
    for b in known_brands:
        try:
            if re.search(r'\b' + re.escape(b) + r'\b', text_to_scan):
                detected_brand = b
                break
        except Exception:
            if b in text_to_scan:
                detected_brand = b
                break
                
    rfq_db_context, has_incomplete_specs, brand_found = query_vendors(category, df_rfq, detected_brand)

    while not rfq_valid and rfq_attempts < 3:
        rfq_attempts += 1
        print(f"\n[STEP 3 - Orchestrator routes request to RFQ Agent (Attempt {rfq_attempts})]")
        
        # STEP 4 - RFQ Agent
        ConversationLogger.log_agent_start("RFQ Agent")
        
        rfq_system = (
            "You are the RFQ Agent. Search Vendor_RFQ_Database.csv and select vendor bids.\n"
            "CRITICAL BRAND FILTERING RULES:\n"
            "1. STRICT BRAND FILTERING: You MUST filter strictly by the REQUESTED BRAND in user request.\n"
            "2. NEVER recommend a different brand (like Apple or Dell) as primary option when requested brand (like Lenovo or HP) exists in database.\n"
            "3. Only show alternative brands if requested brand has absolutely ZERO vendors in database.\n"
            "4. If requested brand vendor has incomplete/missing detailed specifications (RAM/SSD/CPU), you MUST append this exact risk flag to output:\n"
            f"⚠️ RISK FLAG: {detected_brand.upper() if detected_brand else 'Requested'} vendor found but specifications are incomplete. Human CFO review required.\n\n"
            f"Database context:\n\n{rfq_db_context}\n"
        )
        
        rfq_response = call_claude(rfq_system, f"Request details:\n{current_request}\nFeedback:\n{rfq_feedback}")
        
        if brand_found and "⚠️ RISK FLAG" not in rfq_response:
            rfq_response += f"\n\n⚠️ RISK FLAG: {detected_brand.upper()} vendor found but specifications are incomplete. Human CFO review required."

        ConversationLogger.log_agent_output("RFQ Agent", rfq_response)
        history.append({"role": "RFQ Agent", "agent": "RFQ Agent", "content": rfq_response})
        
        # STEP 5 - Orchestrator validates RFQ output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating RFQ)")
        val_prompt = f"Validate RFQ output:\n\n{rfq_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_claude(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            rfq_valid = val_data.get("valid", False)
            rfq_feedback = val_data.get("feedback", "")
        except Exception:
            rfq_valid = "true" in val_response.lower()
            rfq_feedback = "Ensure vendor choices adhere to requested brand rules."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (RFQ Validation)", "content": f"RFQ Valid: {rfq_valid}. Feedback: {rfq_feedback}"})
        
        if rfq_valid:
            rfq_output = rfq_response
            break
            
    if not rfq_valid:
        return history, "Failed - RFQ Validation Loop timed out"
        
    # ----------------------------------------------------
    # STEP 6 - IT Agent verification
    # ----------------------------------------------------
    it_attempts = 0
    it_valid = False
    it_feedback = "Verify if candidate laptops meet specs (RAM, CPU, storage, display)."
    
    requested_brands = [detected_brand] if detected_brand else ['dell', 'hp', 'lenovo']
    specs_context = ""
    for brand in requested_brands:
        specs_context += query_laptop_specs(brand, df_laptop) + "\n\n"
        
    while not it_valid and it_attempts < 3:
        it_attempts += 1
        print(f"\n[STEP 6/7 - IT Agent Technical Review (Attempt {it_attempts})]")
        ConversationLogger.log_agent_start("IT Agent")
        
        it_system = (
            "You are the IT Agent. Verify hardware specs (RAM, CPU, Storage, Display) against database.\n"
            f"Spec sheet context for {', '.join(requested_brands)}:\n\n{specs_context}\n\n"
            "State clearly which models meet or fail technical requirements."
        )
        
        it_response = call_claude(it_system, f"Requirements:\n{current_request}\n\nRFQ options:\n{rfq_output}\n\nFeedback:\n{it_feedback}")
        ConversationLogger.log_agent_output("IT Agent", it_response)
        history.append({"role": "IT Agent", "agent": "IT Agent", "content": it_response})
        
        # STEP 7 - Orchestrator validates IT output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating IT)")
        val_prompt = f"Validate IT compliance output:\n\n{it_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_claude(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            it_valid = val_data.get("valid", False)
            it_feedback = val_data.get("feedback", "")
        except Exception:
            it_valid = "true" in val_response.lower()
            it_feedback = "Ensure all 4 hardware metrics are verified."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (IT Validation)", "content": f"IT Valid: {it_valid}. Feedback: {it_feedback}"})
        
        if it_valid:
            it_output = it_response
            break
            
    if not it_valid:
        return history, "Failed - IT Validation Loop timed out"
        
    # ----------------------------------------------------
    # STEP 8 - Finance Agent scoring (WITH BUDGET FLAG)
    # ----------------------------------------------------
    finance_attempts = 0
    finance_valid = False
    finance_feedback = "Score vendors 0-100 and choose the best one."
    score_context = calculate_finance_scores(df_rfq, category)
    
    while not finance_valid and finance_attempts < 3:
        finance_attempts += 1
        print(f"\n[STEP 8/9 - Finance Agent Scoring (Attempt {finance_attempts})]")
        ConversationLogger.log_agent_start("Finance Agent")
        
        finance_system = (
            "You are the Finance Agent. Score candidates 0-100 and select the single best vendor.\n"
            "CRITICAL FINANCE & BUDGET RULES:\n"
            "1. IT AGENT CROSS-REFERENCING: Read IT Agent technical review. Reference IT Agent flags before scoring. If IT Agent flagged specification issues, reduce vendor score or add risk flag. Never approve vendor without acknowledging IT Agent findings.\n"
            f"2. USER STATED BUDGET ({stated_budget} USD): Compare recommended vendor total price against user stated budget of ${stated_budget}.\n"
            "   - If vendor total price is WITHIN budget ($ <= stated budget) -> proceed normally.\n"
            "   - If vendor total price EXCEEDS stated budget ($ > stated budget) -> you MUST append this exact flag:\n"
            f"     ⚠️ BUDGET FLAG: Vendor price $PRICE exceeds stated budget of ${stated_budget}. Human CFO review required.\n"
            "   - NEVER automatically reject a vendor due to budget -> always pass to Human CFO with budget flag visible.\n\n"
            f"Vendor scoresheet:\n\n{score_context}\n\n"
            "Select highest scoring vendor matching requested brand and explain why."
        )
        
        finance_response = call_claude(finance_system, f"RFQ: {rfq_output}. IT specs: {it_output}. User Stated Budget: ${stated_budget}. Feedback: {finance_feedback}")
        ConversationLogger.log_agent_output("Finance Agent", finance_response)
        history.append({"role": "Finance Agent", "agent": "Finance Agent", "content": finance_response})
        
        # STEP 9 - Orchestrator validates Finance output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating Finance)")
        val_prompt = f"Validate Finance report:\n\n{finance_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_claude(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            fin_valid = val_data.get("valid", False)
            fin_feedback = val_data.get("feedback", "")
        except Exception:
            fin_valid = "true" in val_response.lower()
            fin_feedback = "Ensure single best vendor recommendation."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (Finance Validation)", "content": f"Finance Valid: {fin_valid}. Feedback: {fin_feedback}"})
        
        if fin_valid:
            finance_output = finance_response
            break
            
    if not fin_valid:
        return history, "Failed - Finance Validation Loop timed out"

    # ----------------------------------------------------
    # STEP 10 - CFO Agent budget check (BUDGET & QUANTITY AWARE)
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("CFO Agent")
    
    procurement_units = quantity - available_qty if inv_status == "PARTIAL" else (0 if inv_status == "FULL" else quantity)
    warehouse_units = available_qty if inv_status in ["FULL", "PARTIAL"] else 0

    cfo_system = (
        "You are the CFO Agent in an automated IT procurement system.\n"
        "YOUR SOLE JOB is to perform an automatic budget check against the user's stated budget.\n"
        "CRITICAL INSTRUCTIONS:\n"
        f"1. BUDGET & PRICE AWARENESS: Read the user stated budget (${stated_budget}) and actual vendor price from Finance Agent output. Extract exact numeric prices. NEVER use placeholders like $X or $Y.\n"
        f"2. BUDGET FLAGS: Compare vendor total price against user stated budget of ${stated_budget}. If vendor price exceeds ${stated_budget}, or if a BUDGET FLAG or RISK FLAG exists in previous agent outputs, acknowledge it clearly.\n"
        "3. NO AUTOMATIC REJECTION: Never automatically reject a request. Always pass the evaluation to Human CFO with flags visible.\n"
        f"4. SINGLE ACTUAL QUANTITY ONLY: Only calculate budget for the actual quantity being procured ({procurement_units} unit(s)). DO NOT calculate or show scenarios for other quantities (e.g. 2 units, 5 units).\n"
        f"5. State clearly: '{warehouse_units} unit(s) from warehouse at $0, {procurement_units} unit(s) from vendor at $PRICE each (Total external cost: $TOTAL)'\n"
        f"6. Compare Total External Cost against stated budget of ${stated_budget} and state whether it is within budget or exceeds budget."
    )
    cfo_prompt = (
        f"User Stated Budget: ${stated_budget}\n"
        f"Inventory Breakdown: {warehouse_units} unit(s) in warehouse inventory ($0), {procurement_units} unit(s) required for external procurement.\n"
        f"Finance Report:\n{finance_output}\n\n"
        f"RFQ Bids Context:\n{rfq_output}"
    )
    cfo_response = call_claude(cfo_system, cfo_prompt)
    ConversationLogger.log_agent_output("CFO Agent", cfo_response)
    history.append({"role": "CFO Agent", "agent": "CFO Agent", "content": cfo_response})
    
    # ----------------------------------------------------
    # STEP 11 - Human CFO review
    # ----------------------------------------------------
    print("\n" + "#"*60)
    print("📋 [STEP 11 - HUMAN CFO REVIEW]")
    print("#"*60)
    for step in history:
        print(f"[{step['role']}]: {step['content']}\n" + "-"*40)
        
    human_cfo_input = input("\nHuman CFO, type 'APPROVE' to proceed or 'REJECT' to stop: ").strip().upper()
    history.append({"role": "Human CFO", "agent": "Human CFO", "content": f"Decision: {human_cfo_input}"})
    
    if human_cfo_input != "APPROVE":
        print("\nPROCUREMENT TERMINATED BY HUMAN CFO.")
        return history, "Rejected by Human CFO"
        
    # ----------------------------------------------------
    # STEP 12 - CEO Agent review
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("CEO Agent")
    ceo_system = "You are the CEO Agent. Review transcript and output formal board recommendation report."
    summary_history = "\n".join([f"[{h['role']}]: {h['content']}" for h in history])
    ceo_response = call_claude(ceo_system, f"Complete Workflow Transcript:\n{summary_history}")
    ConversationLogger.log_agent_output("CEO Agent", ceo_response)
    history.append({"role": "CEO Agent", "agent": "CEO Agent", "content": ceo_response})
    
    # ----------------------------------------------------
    # STEP 13 - Human CEO final approval
    # ----------------------------------------------------
    print("\n" + "#"*60)
    print("👑 [STEP 13 - HUMAN CEO FINAL DECISION]")
    print("#"*60)
    print(f"CEO report:\n{ceo_response}\n")
    
    human_ceo_input = input("Human CEO, type 'APPROVE' to authorize or 'REJECT' to deny: ").strip().upper()
    history.append({"role": "Human CEO", "agent": "Human CEO", "content": f"Final Decision: {human_ceo_input}"})
    
    status = "PROCUREMENT APPROVED SUCCESSFULLY" if human_ceo_input == "APPROVE" else "PROCUREMENT DENIED BY HUMAN CEO"
    print(f"\n📢 Final Outcome: {status}\n")
    return history, status

# ==========================================
# VERSION 2: OPENAI GPT-4O WORKFLOW
# ==========================================

def run_workflow_openai(
    request_text: str,
    df_inventory: pd.DataFrame,
    df_rfq: pd.DataFrame,
    df_laptop: pd.DataFrame,
    openai_client,
    model_name: str = "gpt-4o"
) -> Tuple[List[Dict[str, str]], str]:
    """
    Executes the 13-step IT procurement workflow using ONLY OpenAI GPT-4o.
    """
    history = []
    
    def call_openai(system_prompt: str, user_prompt: str) -> str:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )
        return response.choices[0].message.content

    # ----------------------------------------------------
    # STEP 1 - Human opens ticket
    # ----------------------------------------------------
    print(f"\n[STEP 1 - Human opens ticket]\nRequest: {request_text}\n")
    history.append({"role": "Human", "agent": "Human", "content": request_text})
    
    # ----------------------------------------------------
    # STEP 2 - Proxy Agent
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("Proxy Agent")
    proxy_system = (
        "You are the Proxy Agent. Read the human's IT procurement request and output a short, simple summary.\n"
        "DO NOT use markdown formatting, tables, bold headers, bullet points, or emojis.\n"
        "Your output MUST strictly follow this exact 5-line format:\n\n"
        "REWRITTEN_REQUEST: <short 1-line clear description of requested item and specs>\n"
        "CATEGORY: <item category e.g. Laptop>\n"
        "SEARCH_KEYWORDS: <space separated keywords with letters and numbers only>\n"
        "QUANTITY: <integer quantity requested>\n"
        "BUDGET: <integer budget in USD extracted from user request, e.g. 1000. If no budget mentioned, output 5000>"
    )
    proxy_response = call_openai(proxy_system, f"Human Request: {request_text}")
    ConversationLogger.log_agent_output("Proxy Agent", proxy_response)
    history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": proxy_response})
    
    rewritten_req, category, search_term, quantity, stated_budget = parse_proxy_output(proxy_response, request_text)
    
    inv_status, inv_msg, available_qty, matched_product = query_inventory(search_term, category, df_inventory, quantity, request_text)
    print(f"Inventory Search Results [{inv_status}]:\n{inv_msg}\n")
    
    if inv_status == "FULL":
        close_msg = f"TICKET CLOSED: All {quantity} unit(s) of '{matched_product}' exist in stock. Please proceed to warehouse."
        print(close_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": close_msg})
        return history, "Closed - Item in Inventory"
    elif inv_status == "PARTIAL":
        needed_qty = quantity - available_qty
        partial_msg = f"PARTIAL INVENTORY: {available_qty} unit(s) of '{matched_product}' available in warehouse. Routing remaining {needed_qty} unit(s) to Orchestrator Agent for procurement."
        print(partial_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": partial_msg})
        current_request = f"{rewritten_req} (Quantity Required: {needed_qty} units, User Budget: ${stated_budget})"
    else:
        notFound_msg = f"NOT IN INVENTORY: Item not available in stock. Passing full request for {quantity} unit(s) to Orchestrator Agent."
        print(notFound_msg)
        history.append({"role": "Proxy Agent", "agent": "Proxy Agent", "content": notFound_msg})
        current_request = f"{rewritten_req} (Quantity Required: {quantity} units, User Budget: ${stated_budget})"

    rfq_output = ""
    it_output = ""
    finance_output = ""
    
    # ----------------------------------------------------
    # STEP 3 - Orchestrator Agent routes to RFQ Agent
    # ----------------------------------------------------
    orchestrator_system = (
        "You are the Orchestrator Agent. Route requests and validate agent reports.\n"
        "When validating, respond ONLY in structured JSON format: {\"valid\": true/false, \"feedback\": \"description\"}"
    )
    
    rfq_attempts = 0
    rfq_valid = False
    rfq_feedback = "Please retrieve the top vendors matching requested brand from Vendor_RFQ_Database.csv."
    
    text_to_scan = f"{request_text} {current_request}".lower()
    known_brands = ['dell', 'hp', 'lenovo', 'apple', 'acer', 'asus', 'msi', 'infinix', 'tecno', 'microsoft']
    detected_brand = ""
    for b in known_brands:
        try:
            if re.search(r'\b' + re.escape(b) + r'\b', text_to_scan):
                detected_brand = b
                break
        except Exception:
            if b in text_to_scan:
                detected_brand = b
                break
                
    rfq_db_context, has_incomplete_specs, brand_found = query_vendors(category, df_rfq, detected_brand)

    while not rfq_valid and rfq_attempts < 3:
        rfq_attempts += 1
        print(f"\n[STEP 3 - Orchestrator routes request to RFQ Agent (Attempt {rfq_attempts})]")
        
        # STEP 4 - RFQ Agent
        ConversationLogger.log_agent_start("RFQ Agent")
        
        rfq_system = (
            "You are the RFQ Agent. Search Vendor_RFQ_Database.csv and select vendor bids.\n"
            "CRITICAL BRAND FILTERING RULES:\n"
            "1. STRICT BRAND FILTERING: You MUST filter strictly by the REQUESTED BRAND in user request.\n"
            "2. NEVER recommend a different brand (like Apple or Dell) as primary option when requested brand (like Lenovo or HP) exists in database.\n"
            "3. Only show alternative brands if requested brand has absolutely ZERO vendors in database.\n"
            "4. If requested brand vendor has incomplete/missing detailed specifications (RAM/SSD/CPU), you MUST append this exact risk flag to output:\n"
            f"⚠️ RISK FLAG: {detected_brand.upper() if detected_brand else 'Requested'} vendor found but specifications are incomplete. Human CFO review required.\n\n"
            f"Database context:\n\n{rfq_db_context}\n"
        )
        
        rfq_response = call_openai(rfq_system, f"Request details:\n{current_request}\nFeedback:\n{rfq_feedback}")
        
        if brand_found and "⚠️ RISK FLAG" not in rfq_response:
            rfq_response += f"\n\n⚠️ RISK FLAG: {detected_brand.upper()} vendor found but specifications are incomplete. Human CFO review required."

        ConversationLogger.log_agent_output("RFQ Agent", rfq_response)
        history.append({"role": "RFQ Agent", "agent": "RFQ Agent", "content": rfq_response})
        
        # STEP 5 - Orchestrator validates RFQ output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating RFQ)")
        val_prompt = f"Validate RFQ output:\n\n{rfq_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_openai(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            rfq_valid = val_data.get("valid", False)
            rfq_feedback = val_data.get("feedback", "")
        except Exception:
            rfq_valid = "true" in val_response.lower()
            rfq_feedback = "Ensure vendor choices adhere to requested brand rules."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (RFQ Validation)", "content": f"RFQ Valid: {rfq_valid}. Feedback: {rfq_feedback}"})
        
        if rfq_valid:
            rfq_output = rfq_response
            break
            
    if not rfq_valid:
        return history, "Failed - RFQ Validation Loop timed out"
        
    # ----------------------------------------------------
    # STEP 6 - IT Agent verification
    # ----------------------------------------------------
    it_attempts = 0
    it_valid = False
    it_feedback = "Verify if candidate laptops meet specs (RAM, CPU, storage, display)."
    
    requested_brands = [detected_brand] if detected_brand else ['dell', 'hp', 'lenovo']
    specs_context = ""
    for brand in requested_brands:
        specs_context += query_laptop_specs(brand, df_laptop) + "\n\n"
        
    while not it_valid and it_attempts < 3:
        it_attempts += 1
        print(f"\n[STEP 6/7 - IT Agent Technical Review (Attempt {it_attempts})]")
        ConversationLogger.log_agent_start("IT Agent")
        
        it_system = (
            "You are the IT Agent. Verify hardware specs (RAM, CPU, Storage, Display) against database.\n"
            f"Spec sheet context for {', '.join(requested_brands)}:\n\n{specs_context}\n\n"
            "State clearly which models meet or fail technical requirements."
        )
        
        it_response = call_openai(it_system, f"Requirements:\n{current_request}\n\nRFQ options:\n{rfq_output}\n\nFeedback:\n{it_feedback}")
        ConversationLogger.log_agent_output("IT Agent", it_response)
        history.append({"role": "IT Agent", "agent": "IT Agent", "content": it_response})
        
        # STEP 7 - Orchestrator validates IT output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating IT)")
        val_prompt = f"Validate IT compliance output:\n\n{it_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_openai(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            it_valid = val_data.get("valid", False)
            it_feedback = val_data.get("feedback", "")
        except Exception:
            it_valid = "true" in val_response.lower()
            it_feedback = "Ensure all 4 hardware metrics are verified."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (IT Validation)", "content": f"IT Valid: {it_valid}. Feedback: {it_feedback}"})
        
        if it_valid:
            it_output = it_response
            break
            
    if not it_valid:
        return history, "Failed - IT Validation Loop timed out"
        
    # ----------------------------------------------------
    # STEP 8 - Finance Agent scoring (WITH IT CROSS-REFERENCING & BUDGET FLAG)
    # ----------------------------------------------------
    finance_attempts = 0
    finance_valid = False
    finance_feedback = "Score vendors 0-100 and choose the best one."
    score_context = calculate_finance_scores(df_rfq, category)
    
    while not finance_valid and finance_attempts < 3:
        finance_attempts += 1
        print(f"\n[STEP 8/9 - Finance Agent Scoring (Attempt {finance_attempts})]")
        ConversationLogger.log_agent_start("Finance Agent")
        
        finance_system = (
            "You are the Finance Agent. Score candidates 0-100 and select the single best vendor.\n"
            "CRITICAL FINANCE & BUDGET RULES:\n"
            "1. IT AGENT CROSS-REFERENCING: Read IT Agent technical review. Reference IT Agent flags before scoring. If IT Agent flagged specification issues, reduce vendor score or add risk flag. Never approve vendor without acknowledging IT Agent findings.\n"
            f"2. USER STATED BUDGET ({stated_budget} USD): Compare recommended vendor total price against user stated budget of ${stated_budget}.\n"
            "   - If vendor total price is WITHIN budget ($ <= stated budget) -> proceed normally.\n"
            "   - If vendor total price EXCEEDS stated budget ($ > stated budget) -> you MUST append this exact flag:\n"
            f"     ⚠️ BUDGET FLAG: Vendor price $PRICE exceeds stated budget of ${stated_budget}. Human CFO review required.\n"
            "   - NEVER automatically reject a vendor due to budget -> always pass to Human CFO with budget flag visible.\n\n"
            f"Vendor scoresheet:\n\n{score_context}\n\n"
            "Select highest scoring vendor matching requested brand and explain why."
        )
        
        finance_response = call_openai(finance_system, f"RFQ options:\n{rfq_output}\n\nIT Agent Review:\n{it_output}\n\nUser Stated Budget: ${stated_budget}\n\nFeedback:\n{finance_feedback}")
        ConversationLogger.log_agent_output("Finance Agent", finance_response)
        history.append({"role": "Finance Agent", "agent": "Finance Agent", "content": finance_response})
        
        # STEP 9 - Orchestrator validates Finance output
        ConversationLogger.log_agent_start("Orchestrator Agent (Validating Finance)")
        val_prompt = f"Validate Finance report:\n\n{finance_response}\n\nRespond ONLY with JSON: {{\"valid\": true/false, \"feedback\": \"text\"}}"
        val_response = call_openai(orchestrator_system, val_prompt)
        print(f"Orchestrator validation: {val_response}")
        
        try:
            cleaned_json = re.sub(r"```json|```", "", val_response).strip()
            val_data = json.loads(cleaned_json)
            fin_valid = val_data.get("valid", False)
            fin_feedback = val_data.get("feedback", "")
        except Exception:
            fin_valid = "true" in val_response.lower()
            fin_feedback = "Ensure single best vendor recommendation."
            
        history.append({"role": "Orchestrator Agent", "agent": "Orchestrator (Finance Validation)", "content": f"Finance Valid: {fin_valid}. Feedback: {fin_feedback}"})
        
        if fin_valid:
            finance_output = finance_response
            break
            
    if not fin_valid:
        return history, "Failed - Finance Validation Loop timed out"

    # ----------------------------------------------------
    # STEP 10 - CFO Agent budget validation (BUDGET & QUANTITY AWARE)
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("CFO Agent")
    
    procurement_units = quantity - available_qty if inv_status == "PARTIAL" else (0 if inv_status == "FULL" else quantity)
    warehouse_units = available_qty if inv_status in ["FULL", "PARTIAL"] else 0

    cfo_system = (
        "You are the CFO Agent in an automated IT procurement system.\n"
        "YOUR SOLE JOB is to perform an automatic budget check against the user's stated budget.\n"
        "CRITICAL INSTRUCTIONS:\n"
        f"1. BUDGET & PRICE AWARENESS: Read the user stated budget (${stated_budget}) and actual vendor price from Finance Agent output. Extract exact numeric prices. NEVER use placeholders like $X or $Y.\n"
        f"2. BUDGET FLAGS: Compare vendor total price against user stated budget of ${stated_budget}. If vendor price exceeds ${stated_budget}, or if a BUDGET FLAG or RISK FLAG exists in previous agent outputs, acknowledge it clearly.\n"
        "3. NO AUTOMATIC REJECTION: Never automatically reject a request. Always pass the evaluation to Human CFO with flags visible.\n"
        f"4. SINGLE ACTUAL QUANTITY ONLY: Only calculate budget for the actual quantity being procured ({procurement_units} unit(s)). DO NOT calculate or show scenarios for other quantities (e.g. 2 units, 5 units).\n"
        f"5. State clearly: '{warehouse_units} unit(s) from warehouse at $0, {procurement_units} unit(s) from vendor at $PRICE each (Total external cost: $TOTAL)'\n"
        f"6. Compare Total External Cost against stated budget of ${stated_budget} and state whether it is within budget or exceeds budget."
    )
    cfo_prompt = (
        f"User Stated Budget: ${stated_budget}\n"
        f"Inventory Breakdown: {warehouse_units} unit(s) in warehouse inventory ($0), {procurement_units} unit(s) required for external procurement.\n"
        f"Finance Report:\n{finance_output}\n\n"
        f"RFQ Bids Context:\n{rfq_output}"
    )
    cfo_response = call_openai(cfo_system, cfo_prompt)
    ConversationLogger.log_agent_output("CFO Agent", cfo_response)
    history.append({"role": "CFO Agent", "agent": "CFO Agent", "content": cfo_response})
    
    # ----------------------------------------------------
    # STEP 11 - Human CFO review
    # ----------------------------------------------------
    print("\n" + "#"*60)
    print("📋 [STEP 11 - HUMAN CFO REVIEW]")
    print("#"*60)
    for step in history:
        print(f"[{step['role']}]: {step['content']}\n" + "-"*40)
        
    human_cfo_input = input("\nHuman CFO, type 'APPROVE' to proceed or 'REJECT' to stop: ").strip().upper()
    history.append({"role": "Human CFO", "agent": "Human CFO", "content": f"Decision: {human_cfo_input}"})
    
    if human_cfo_input != "APPROVE":
        print("\nPROCUREMENT TERMINATED BY HUMAN CFO.")
        return history, "Rejected by Human CFO"
        
    # ----------------------------------------------------
    # STEP 12 - CEO Agent review
    # ----------------------------------------------------
    ConversationLogger.log_agent_start("CEO Agent")
    ceo_system = "You are the CEO Agent. Review transcript and output formal board recommendation report."
    summary_history = "\n".join([f"[{h['role']}]: {h['content']}" for h in history])
    ceo_response = call_openai(ceo_system, f"Complete Workflow Transcript:\n{summary_history}")
    ConversationLogger.log_agent_output("CEO Agent", ceo_response)
    history.append({"role": "CEO Agent", "agent": "CEO Agent", "content": ceo_response})
    
    # ----------------------------------------------------
    # STEP 13 - Human CEO final approval
    # ----------------------------------------------------
    print("\n" + "#"*60)
    print("👑 [STEP 13 - HUMAN CEO FINAL DECISION]")
    print("#"*60)
    print(f"CEO report:\n{ceo_response}\n")
    
    human_ceo_input = input("Human CEO, type 'APPROVE' to authorize or 'REJECT' to deny: ").strip().upper()
    history.append({"role": "Human CEO", "agent": "Human CEO", "content": f"Final Decision: {human_ceo_input}"})
    
    status = "PROCUREMENT APPROVED SUCCESSFULLY" if human_ceo_input == "APPROVE" else "PROCUREMENT DENIED BY HUMAN CEO"
    print(f"\n📢 Final Outcome: {status}\n")
    return history, status

# ==========================================
# 4. NOTEBOOK INITIALIZATION / ENTRYPOINT
# ==========================================

if __name__ == "__main__":
    df_inventory, df_rfq, df_laptop = load_databases()
    
    print("=== STEP 1: ENTER YOUR IT PROCUREMENT REQUEST TICKET ===")
    user_request_input = input("Type your IT procurement request (or press Enter for default): ").strip()
    
    if not user_request_input:
        user_request_input = "I need to procure 2 HP Business Laptops for university laboratory experiments. Requirements: at least 16GB RAM, 512GB SSD, Intel i5 processor, 15.6 inch screen size. Budget is $1000."
        print(f"Using default request: {user_request_input}")
    else:
        print(f"Ticket request received: {user_request_input}")
