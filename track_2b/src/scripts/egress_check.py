import sys
import urllib.error
import urllib.request

MODEL_URL = "http://apertus:8080/health"
OUTSIDE_URLS = ["https://api.publicai.co", "https://huggingface.co", "https://1.1.1.1"]


def reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=5)
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


def main() -> int:
    model = reachable(MODEL_URL)
    outside = {url: reachable(url) for url in OUTSIDE_URLS}
    print(f"model   {MODEL_URL}: {'reachable' if model else 'NOT reachable'}")
    for url, ok in outside.items():
        print(f"outside {url}: {'REACHABLE' if ok else 'blocked'}")
    sealed = model and not any(outside.values())
    print("OK: the app reaches the model and nothing else" if sealed else "FAIL")
    return 0 if sealed else 1


if __name__ == "__main__":
    sys.exit(main())