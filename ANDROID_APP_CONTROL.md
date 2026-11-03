# Arc1 Android app control

Arc1 can queue a limited set of Android actions from an explicit chat request:

- Open an installed app by its visible name or Android package.
- Tap a visible text label or a screen coordinate.
- Enter text into a normal editable field.
- Scroll, wait, or use Back, Home, and Recents.

## Enable the service

1. Install and open the Arc1 Android app.
2. Ask Arc1 to control an installed app.
3. Android opens Accessibility settings on the first request.
4. Select **Arc1 App Control** and enable it.
5. Return to Arc1 and send the request again.

Android requires the user to enable this service manually. Arc1 does not bypass
that consent screen. Text entry into fields marked as passwords is blocked.

## Local backend

The Android emulator connects to the backend at `http://10.0.2.2:8000` by
default. Start the backend on port 8000 before sending a prompt. For a physical
phone or hosted backend, build with `ARC_API_BASE_URL` set to an address the
phone can reach.

## Safe first test

Use a simple installed app first:

`Open Settings.`

Then test a visible control:

`Open Settings and tap Network & internet.`

Do not ask Arc1 to enter passwords, PINs, payment data, or one-time codes.
