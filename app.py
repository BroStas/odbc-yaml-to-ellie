import streamlit as st
import yaml
import requests
from streamlit.components.v1 import html
import uuid

# Configure page layout
st.set_page_config(page_title="ODBC Yaml to Ellie importer", layout="wide")

# Title
st.title("ODBC Yaml to Ellie importer")

# File uploader
uploaded_file = st.file_uploader("Upload YAML file", type=["yaml","yml"])
model_def = None
content = None
if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    # Parse YAML
    try:
        model_def = yaml.safe_load(content)
    except Exception as e:
        st.error(f"Error parsing YAML: {e}")

# Mermaid generator
def generate_mermaid(defn):
    diagram = "erDiagram\n"
    # Entities or schema
    entities = defn.get("entities") or defn.get("schema") or []
    for ent in entities:
        name = ent.get("name")
        diagram += f"    {name} {{\n"
        # Loop over each property/attribute
        props = ent.get("attributes") or ent.get("properties") or []
        for attr in props:
            # Basic type and name
            t = attr.get("logicalType", attr.get("type", "string"))
            n = attr.get("name")
            # Build suffix from flags
            flags = []
            if attr.get("primaryKey"): flags.append("PK")
            if attr.get("required"): flags.append("R")
            if attr.get("unique"): flags.append("U")
            # Append suffix to attribute name
            name_with_flags = f"{n}_{'_'.join(flags)}" if flags else n
            # Emit field
            diagram += f"        {t} {name_with_flags}\n"
        diagram += "    }\n"
    # Relationships from logicalRelationships
    for ent in entities:
        for cp in ent.get("customProperties", []):
            if cp.get("property") == "logicalRelationships":
                for rel in cp.get("value", []):
                    src = rel.get("from","").strip("()").split(".")[0]
                    dst = rel.get("to","").strip("()").split(".")[0]
                    cf = rel.get("cardinalityFrom")
                    ct = rel.get("cardinalityTo")
                    def m(c):
                        return {"one":"||","zeroOrMany":"o{","zeroOrOne":"o|","oneOrMany":"|{"}.get(c, "--")
                    diagram += f"    {src} {m(cf)}--{m(ct)} {dst} : \"{rel.get('label','')}\"\n"
    return diagram

# Graphviz DOT generator for multi-column nodes
def generate_dot(defn, show_full_metadata=False, dup_handling="Ignore Duplicates", selected_tables=None):
    yaml_entities = defn.get("schema") or defn.get("entities") or []
    entity_list = []
    name_count = {}
    entity_map = {}
    if dup_handling == "Ignore Duplicates":
        seen = set()
        for ent in yaml_entities:
            name = ent.get("name")
            if name in seen:
                continue
            seen.add(name)
            entity_list.append(ent)
    elif dup_handling == "Add Postfix":
        for ent in yaml_entities:
            name = ent.get("name")
            if name not in name_count:
                name_count[name] = 1
                entity_list.append(ent)
            else:
                name_count[name] += 1
                ent = ent.copy()
                ent["name"] = f"{name}_{name_count[name]}"
                entity_list.append(ent)
    elif dup_handling == "Combine Attributes":
        for ent in yaml_entities:
            name = ent.get("name")
            if name not in entity_map:
                entity_map[name] = ent.copy()
                props = ent.get("properties") or ent.get("attributes") or []
                entity_map[name]["_all_attributes"] = {a.get("name"): a.copy() for a in props}
            else:
                props = ent.get("properties") or ent.get("attributes") or []
                for a in props:
                    if a.get("name") not in entity_map[name]["_all_attributes"]:
                        entity_map[name]["_all_attributes"][a.get("name")] = a.copy()
        for ent in entity_map.values():
            ent = ent.copy()
            all_attrs = list(ent.pop("_all_attributes").values())
            ent["properties"] = all_attrs
            entity_list.append(ent)
    # Filter by selected tables if provided
    if selected_tables is not None:
        entity_list = [e for e in entity_list if e.get("name") in selected_tables]
    entity_names = set(e.get("name") for e in entity_list)
    # Build attribute metadata for preview (simulate what will be sent)
    attr_meta_map = {}
    for ent in entity_list:
        props = ent.get("properties") or ent.get("attributes") or []
        attr_meta_map[ent.get("name")] = []
        for attr in props:
            flags = []
            if attr.get("primaryKey"): flags.append("PK")
            if attr.get("required"): flags.append("R")
            if attr.get("unique"): flags.append("U")
            # We'll add FK below
            type_ = attr.get("physicalType") or attr.get("logicalType") or attr.get("type", "string")
            desc = attr.get("description", "")
            attr_meta_map[ent.get("name")].append({
                "name": attr.get("name"),
                "type": type_,
                "flags": flags,
                "desc": desc
            })
    # Mark FK attributes based on relationships
    for ent in entity_list:
        for cp in ent.get("customProperties", []):
            if cp.get("property") == "logicalRelationships":
                for rel in cp.get("value", []):
                    src_raw = rel.get("from", "").strip("()")
                    dst_raw = rel.get("to", "").strip("()")
                    src_ent = src_raw.split(".")[0]
                    dst_ent = dst_raw.split(".")[0]
                    if src_ent not in entity_names or dst_ent not in entity_names:
                        continue
                    d_attrs = [a.split('.')[-1] for a in dst_raw.split(',')]
                    # Mark FK in the target entity's attributes
                    for attr in attr_meta_map[dst_ent]:
                        if attr["name"] in d_attrs and "FK" not in attr["flags"]:
                            attr["flags"].append("FK")
    # Build DOT
    dot = 'digraph G {\n  node [shape=record,fontname="Arial"];\n'
    for ent in entity_list:
        node_id = ent.get("name").replace("-", "_")
        fields = []
        for attr in attr_meta_map[ent.get("name")]:
            if show_full_metadata:
                flag_str = (" (" + ",".join(attr["flags"]) + ")") if attr["flags"] else ""
                desc_str = f" // {attr['desc']}" if attr["desc"] else ""
                fields.append(f"{attr['name']}{flag_str}: {attr['type']}{desc_str}")
            else:
                # Only show PK/FK flags
                simple_flags = [f for f in attr["flags"] if f in ("PK", "FK")]
                flag_str = (" (" + ",".join(simple_flags) + ")") if simple_flags else ""
                fields.append(f"{attr['name']}{flag_str}: {attr['type']}")
        label = "{" + ent.get("name") + "|" + "\\l".join(fields) + "\\l" + "}"
        dot += f'  {node_id} [label="{label}"]\n'
    # Relationships (only between deduped entities)
    for ent in entity_list:
        for cp in ent.get("customProperties", []):
            if cp.get("property") == "logicalRelationships":
                for rel in cp.get("value", []):
                    src = rel.get("from", "").strip("()").split(".")[0].replace("-", "_")
                    dst = rel.get("to", "").strip("()").split(".")[0].replace("-", "_")
                    # Only draw if both entities exist
                    if src not in entity_names or dst not in entity_names:
                        continue
                    label = rel.get("label", "")
                    dot += f'  {src} -> {dst} [label="{label}"]\n'
    dot += "}\n"
    return dot

# If parsed, show diagram and YAML
if model_def:
    show_full_metadata = st.checkbox("Show full attribute metadata", value=False, help="Toggle to show all attribute metadata or just name/type/PK/FK.")
    dup_handling = st.sidebar.selectbox(
        "Duplicate Table Handling",
        ["Add Postfix", "Ignore Duplicates", "Combine Attributes"],
        help="How to handle tables with duplicate names in the YAML."
    )
    # Table selection logic
    # Build the entity list using the selected duplicate handling logic (but don't build payload yet)
    yaml_entities = model_def.get("schema") or model_def.get("entities") or []
    entity_list = []
    name_count = {}
    entity_map = {}
    if dup_handling == "Ignore Duplicates":
        seen = set()
        for ent in yaml_entities:
            name = ent.get("name")
            if name in seen:
                continue
            seen.add(name)
            entity_list.append(ent)
    elif dup_handling == "Add Postfix":
        for ent in yaml_entities:
            name = ent.get("name")
            if name not in name_count:
                name_count[name] = 1
                entity_list.append(ent)
            else:
                name_count[name] += 1
                ent = ent.copy()
                ent["name"] = f"{name}_{name_count[name]}"
                entity_list.append(ent)
    elif dup_handling == "Combine Attributes":
        for ent in yaml_entities:
            name = ent.get("name")
            if name not in entity_map:
                entity_map[name] = ent.copy()
                props = ent.get("properties") or ent.get("attributes") or []
                entity_map[name]["_all_attributes"] = {a.get("name"): a.copy() for a in props}
            else:
                props = ent.get("properties") or ent.get("attributes") or []
                for a in props:
                    if a.get("name") not in entity_map[name]["_all_attributes"]:
                        entity_map[name]["_all_attributes"][a.get("name")] = a.copy()
        for ent in entity_map.values():
            ent = ent.copy()
            all_attrs = list(ent.pop("_all_attributes").values())
            ent["properties"] = all_attrs
            entity_list.append(ent)
    all_entity_names = [e.get("name") for e in entity_list]
    import_all_tables = st.sidebar.checkbox("Import all tables", value=True)
    selected_tables = all_entity_names
    if not import_all_tables:
        selected_tables = st.sidebar.multiselect(
            "Select tables to import",
            options=all_entity_names,
            default=all_entity_names
        )
    dot = generate_dot(model_def, show_full_metadata, dup_handling, selected_tables)
    with st.expander("Model Diagram", expanded=True):
        st.graphviz_chart(dot)
    with st.expander("YAML Content", expanded=False):
        st.code(content, language="yaml")

    # Sidebar for Ellie settings
    st.sidebar.header("Ellie Import Settings")
    # Step 1: Connect to Ellie
    if "ellie_connected" not in st.session_state:
        st.session_state.ellie_connected = False
    slug = st.sidebar.text_input("Ellie Subdomain (slug)", value="" if not st.session_state.get("slug") else st.session_state["slug"])
    api_key = st.sidebar.text_input("Ellie API Key", type="password", value="" if not st.session_state.get("api_key") else st.session_state["api_key"])
    connect_clicked = st.sidebar.button("Connect")
    base_url = f"https://{slug}.ellie.ai" if slug else "https://ellie.ai"
    folders = []
    folder_id = None
    fm = {}
    if connect_clicked:
        # Try to fetch folders to test connection
        r = requests.get(f"{base_url}/api/v1/folders", params={"token": api_key})
        if r.ok:
            st.session_state.ellie_connected = True
            st.session_state.slug = slug
            st.session_state.api_key = api_key
            data = r.json()
            if isinstance(data, dict) and 'folders' in data:
                folders = data['folders'] or []
            elif isinstance(data, list):
                folders = data
            else:
                folders = []
            for f in folders:
                name = f.get('name') or f.get('folderName')
                fid = f.get('folderId', f.get('id'))
                if name and fid is not None:
                    fm[name] = fid
            st.success("Connected to Ellie! Continue below.")
        else:
            st.session_state.ellie_connected = False
            st.sidebar.error(f"Error connecting to Ellie: {r.status_code}")
    elif st.session_state.ellie_connected and st.session_state.get("slug") and st.session_state.get("api_key"):
        # Already connected in session
        slug = st.session_state["slug"]
        api_key = st.session_state["api_key"]
        base_url = f"https://{slug}.ellie.ai" if slug else "https://ellie.ai"
        r = requests.get(f"{base_url}/api/v1/folders", params={"token": api_key})
        if r.ok:
            data = r.json()
            if isinstance(data, dict) and 'folders' in data:
                folders = data['folders'] or []
            elif isinstance(data, list):
                folders = data
            else:
                folders = []
            for f in folders:
                name = f.get('name') or f.get('folderName')
                fid = f.get('folderId', f.get('id'))
                if name and fid is not None:
                    fm[name] = fid
    # Step 2: Show rest of sidebar only if connected
    if st.session_state.ellie_connected and fm:
        model_name = st.sidebar.text_input("Model Name", value="Sample Model Name")
        progress_status = st.sidebar.selectbox("Progress Status", [
            "Work in Progress",
            "Waiting for Approval",
            "Approved",
            "In Production"
        ])
        choice = st.sidebar.selectbox("Folder", list(fm.keys()))
        folder_id = fm.get(choice)
        if st.sidebar.button("Create Model in Ellie"):
            if not api_key or not folder_id:
                st.sidebar.error("API key and folder required.")
            else:
                # Initialize payload for physical model import
                entity_ids = {}
                payload = {
                    "model": {
                        "name": model_name,
                        "level": "physical",
                        "folderId": folder_id,
                        "entities": [],
                        "relationships": []
                    }
                }
                # Process entities from YAML schema with duplicate handling and table selection
                entities_for_payload = [e for e in entity_list if e.get("name") in selected_tables]
                entity_ids = {}
                for ent in entities_for_payload:
                    name = ent.get("name")
                    ent_id = str(uuid.uuid4())
                    entity_ids[name] = ent_id
                    props = ent.get("properties") or ent.get("attributes") or []
                    attributes = []
                    for idx, attr in enumerate(props):
                        meta = {cp.get("property"): cp.get("value") for cp in attr.get("customProperties", [])}
                        # Map standard fields
                        meta["PK"] = bool(attr.get("primaryKey", False))
                        meta["Not null"] = bool(attr.get("required", False))
                        meta["Unique"] = bool(attr.get("unique", False))
                        meta["Data type"] = attr.get("physicalType") or attr.get("logicalType", "")
                        meta["description"] = attr.get("description", "")
                        if "default" in attr:
                            meta["Default"] = attr["default"]
                        if "partitionedBy" in attr:
                            meta["Partitioned by"] = attr["partitionedBy"]
                        attributes.append({
                            "name": attr.get("name"),
                            "metadata": meta,
                            "order": idx + 1
                        })
                    payload["model"]["entities"].append({
                        "id": ent_id,
                        "name": name,
                        "attributes": attributes
                    })
                # Now process relationships only after all entities are created
                # Also, collect FK targets for later FK flagging
                fk_targets = []
                for ent in yaml_entities:
                    for cp in ent.get("customProperties", []):
                        if cp.get("property") == "logicalRelationships":
                            for rel in cp.get("value", []):
                                src_raw = rel.get("from", "").strip("()")
                                dst_raw = rel.get("to", "").strip("()")
                                src_ent = src_raw.split(".")[0]
                                dst_ent = dst_raw.split(".")[0]
                                # Only add relationship if both entities exist and are selected
                                if src_ent not in entity_ids or dst_ent not in entity_ids:
                                    continue
                                cf_raw = rel.get("cardinalityFrom")
                                ct_raw = rel.get("cardinalityTo")
                                # Only support one-to-one and one-to-many for physical models
                                if cf_raw in ("one", "zeroOrOne") and ct_raw in ("one", "zeroOrOne"):
                                    start_type, end_type = 'one', 'one'
                                elif (cf_raw in ("one", "zeroOrOne") and ct_raw in ("zeroOrMany", "oneOrMany")) or (cf_raw in ("zeroOrMany", "oneOrMany") and ct_raw in ("one", "zeroOrOne")):
                                    start_type, end_type = 'one', 'many'
                                else:
                                    continue
                                s_attrs = [a.split('.')[-1] for a in src_raw.split(',')]
                                d_attrs = [a.split('.')[-1] for a in dst_raw.split(',')]
                                payload["model"]["relationships"].append({
                                    "sourceEntity": {
                                        "id": entity_ids.get(src_ent),
                                        "name": src_ent,
                                        "startType": start_type,
                                        "attributeNames": s_attrs
                                    },
                                    "targetEntity": {
                                        "id": entity_ids.get(dst_ent),
                                        "name": dst_ent,
                                        "endType": end_type,
                                        "attributeNames": d_attrs
                                    },
                                    "description": []
                                })
                                # Collect FK targets for later FK flagging
                                fk_targets.append((dst_ent, d_attrs))
                # Set FK=True for attributes referenced in relationships' targetEntity.attributeNames
                entity_map_payload = {e["name"]: e for e in payload["model"]["entities"]}
                for dst_ent, d_attrs in fk_targets:
                    ent = entity_map_payload.get(dst_ent)
                    if not ent:
                        continue
                    for attr in ent["attributes"]:
                        if attr["name"] in d_attrs:
                            attr["metadata"]["FK"] = True
                # POST to Ellie
                resp = requests.post(f"{base_url}/api/v1/models", params={"token": api_key}, json=payload)
                if resp.status_code == 201:
                    st.success(f"Model created with ID {resp.json().get('modelId')}")
                else:
                    st.error(f"Failed to create model: {resp.status_code} {resp.text}") 