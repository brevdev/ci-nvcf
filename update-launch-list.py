import yaml
import sys
import os

def update_launch_list(new_tag):
    if not os.path.exists('launch-list.yml'):
        print("Error: launch-list.yml not found")
        sys.exit(1)

    with open('launch-list.yml', 'r') as file:
        data = yaml.safe_load(file)
    
    if 'fn_image' not in data:
        print("Error: fn_image field not found in launch-list.yml")
        sys.exit(1)

    # update only the tag 
    image_parts = data['fn_image'].rsplit(':', 1)
    if len(image_parts) != 2:
        print("Error: Invalid fn_image format")
        sys.exit(1)

    data['fn_image'] = f"{image_parts[0]}:{new_tag}"
    
    with open('launch-list.yml', 'w') as file:
        yaml.dump(data, file)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_launch_list.py <new_tag>")
        sys.exit(1)
    
    new_tag = sys.argv[1]
    update_launch_list(new_tag)