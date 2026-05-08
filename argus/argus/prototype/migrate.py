import os
import re

areas = {
    'index.html': '',
    'sites.html': 'watchlist/',
    'comparison.html': 'watchlist/',
    'fetch-runs.html': 'watchlist/',
    'snapshots.html': 'watchlist/',
    'custom-comparison.html': 'watchlist/',
    'site-form.html': 'watchlist/',
    'billing.html': 'pricing/',
    'account.html': 'account/',
    'login.html': 'account/',
}

# Create dirs
for dir_name in set(areas.values()):
    if dir_name:
        os.makedirs(os.path.join('/Users/laiyonghao/ai-coding/1tok/argus/prototype', dir_name), exist_ok=True)

files_to_process = list(areas.keys())
base_dir = '/Users/laiyonghao/ai-coding/1tok/argus/prototype'

for filename in files_to_process:
    source_path = os.path.join(base_dir, filename)
    if not os.path.exists(source_path):
        continue
        
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    target_dir = areas[filename]
    
    # Calculate depth
    depth = target_dir.count('/') if target_dir else 0
    prefix = '../' * depth
    
    # Replace asset links
    content = content.replace('href="assets/', f'href="{prefix}assets/')
    content = content.replace('src="assets/', f'src="{prefix}assets/')
    
    # Replace page links
    for page, page_dir in areas.items():
        if page_dir == target_dir: # same directory
            new_link = page
        else:
            new_link = prefix + page_dir + page
            
        # Replace href="page"
        content = re.sub(rf'href="{page}"', f'href="{new_link}"', content)
        # Handle data-login-next-href="page"
        content = re.sub(rf'data-login-next-href="{page}"', f'data-login-next-href="{new_link}"', content)

    # Save to new location
    target_path = os.path.join(base_dir, target_dir, filename)
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)

print("Migration script generated files.")
