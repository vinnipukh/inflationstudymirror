import xml.etree.ElementTree as ET

tree = ET.parse('sitemap.xml')
root = tree.getroot()

print(f"Root tag: {root.tag}")
print(f"Root attrib: {root.attrib}")

# Count url elements
url_count = len(root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'))
print(f"URL elements found (with namespace): {url_count}")

url_count_no_ns = len(root.findall('.//url'))
print(f"URL elements found (without namespace): {url_count_no_ns}")

# Print first 3 URLs
for i, url_elem in enumerate(root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url')[:3]):
    loc = url_elem.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
    if loc is not None:
        print(f"  URL {i+1}: {loc.text}")