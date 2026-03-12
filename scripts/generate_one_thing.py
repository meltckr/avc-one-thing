import anthropic
import os

def generate_one_thing():
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": "Share one interesting thing worth knowing today."}
        ]
    )
    
    return message.content[0].text

def write_html(content):
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AVC One Thing</title>
</head>
<body>
  <h1>AVC One Thing</h1>
  <p>{content}</p>
</body>
</html>"""
    
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w") as f:
        f.write(html)

if __name__ == "__main__":
    content = generate_one_thing()
    write_html(content)
    print("Generated successfully.")
