# Daily Devotional

Universal desktop and Android app, updated from the supplied v10 `main.py`.

## Android APK

Open **Actions → Build Android APK → Run workflow** on GitHub. Choose the branch
containing the update. Download **Daily-Devotional-App** from the completed run's
Artifacts section and extract the APK. Pushes to `main` and the update branch also
start a build.

The workflow uses Python 3.11, Flet 0.28.3, Flutter 3.29.2 and Java 17. It installs
the pinned `requirements.txt`, including the compatible Flet audio extension.
Desktop recording and local Whisper packages are optional and are not included
in the Android build.

To build locally with Python 3.11:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt 'flet-cli==0.28.3'
flet build apk --project devotional --org com.edu.devotional \
  --product 'Daily Devotional' --build-version 10.0.0 --build-number 100
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.
Flet installs its required Flutter, JDK and Android SDK if they are missing.
The APK is written under `build/apk/`. The packaging exclusions in
`pyproject.toml` keep Git metadata, local environments and saved user data out
of the APK. The application ID remains
`com.edu.devotional.devotional`.

These builds use Flet's default debug signing for installation and testing.
Use the same private signing keystore for future builds if they must update an
existing installation; a different signature requires uninstalling that copy.
A store release requires configuring your own release signing credentials.

## Desktop

Run `python main.py` with Python 3.9 or newer. On desktop, the script creates its
own `.venv_win`, `.venv_mac` or `.venv_linux` and installs its required and optional
packages. First startup needs internet access. Android uses its bundled Python
packages and does not run this bootstrap.

Configure your generation and voice provider in **Setup** and **Voice**. Provider
credentials and access to external services are supplied by the user. Settings,
favorites and cached audio are stored in `DailyDevotionalData` beside the script
on desktop, or in the app's private storage on Android.
