import json

def print_json(file_path):
    with open(file_path, "r") as f:
        data = json.load(f)
        print(data)

    return data

def main():
    print_json("processed_url.json")

if __name__ == "__main__":
    main()
        