from verge_browser import VergeClient


def main() -> None:
    client = VergeClient()
    sandbox = client.create_sandbox(alias="handoff-demo", default_url="https://accounts.google.com")
    cdp = client.get_cdp_info(sandbox["id"])
    print("CDP:", cdp["cdp_url"])

    session = client.get_session_url(sandbox["id"])
    print("Send this URL to the human operator:")
    print(session["url"])

    refreshed = client.get_sandbox(sandbox["id"])
    print("Current status:", refreshed["status"])


if __name__ == "__main__":
    main()
