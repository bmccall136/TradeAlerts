import os
import zipfile

# 1) point this at your project folder:
project_dir = r"C:\TradeAlerts"
# 2) put the zip next to it:
output_zip = os.path.join(project_dir, "TradeAlerts_clean.zip")

with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
    for foldername, subfolders, filenames in os.walk(project_dir):
        for filename in filenames:
            # skip the zip we’re creating if you re-run
            if filename == os.path.basename(output_zip):
                continue
            filepath = os.path.join(foldername, filename)
            # store relative paths so the zip has the same folder structure
            arcname = os.path.relpath(filepath, project_dir)
            z.write(filepath, arcname)

print(f"✅ Created {output_zip}")
