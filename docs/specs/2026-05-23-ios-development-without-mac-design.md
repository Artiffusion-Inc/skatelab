# iOS Development Without Mac — Design Spec

> Date: 2026-05-23
> Status: Approved
> Approach: Minimal (CI now, iOS dev later)

## Problem

SkateLab mobile app uses Kotlin Multiplatform with Compose Multiplatform. iOS target is declared (`iosArm64`, `iosSimulatorArm64`) but has no Xcode project, no CI, no device testing capability. Team has no macOS hardware. Need a path to build, test, and ship iOS app without Mac.

## Context

- **KMP shared module**: `mobile/shared/` with `commonMain`, `androidMain`, `iosMain`
- **iOS source set**: 1 file — `IosTokenStorage.kt` (Keychain integration)
- **iosApp/**: Only Swift theme files, no Xcode project, no entry point
- **CI**: `mobile.yml` — Android only, no iOS jobs
- **Budget**: $99/year for Apple Developer Program (when needed)
- **Target devices**: iPhone + iPad (Universal)
- **Timeline**: Android first, iOS after stabilization
- **Constraint**: WireGuard blocked in Russia → SideStore VPN not usable

## Decisions

### D1: CI-first approach

GitHub Actions macOS runner compiles KMP iOS target + builds `.ipa` on every push. No Mac required locally.

**Rationale**: Catches iOS-specific compilation errors early. Shared code is 95% common — CI validates the remaining 5%.

### D2: AltServer-Linux for local testing

Use `ghcr.io/sidestore/altcon` (Podman/Docker) on Linux machine with USB cable for sideloading `.ipa` onto iPhone/iPad. No Mac needed.

**Rationale**: WireGuard/SideStore blocked in Russia. USB sideloading works without VPN. 7-day certificate is acceptable for development phase.

### D3: TestFlight for beta distribution (post Apple Developer enrollment)

When Apple Developer Program is purchased ($99/year), switch from AltServer sideloading to TestFlight distribution via App Store Connect API.

**Rationale**: TestFlight gives 1-year certificates, up to 10,000 external testers, no VPN required, no USB cable required.

### D4: Blacksmith for macOS CI (private repo)

Blacksmith provides macOS M2 Pro runners with 3,000 free minutes/month. Fallback: GitHub Actions `macos-latest` runner (2,000 min free for private repos, but macOS ×10 multiplier = ~200 real minutes).

**Rationale**: Private repo = limited free macOS minutes on GitHub. Blacksmith 3,000 min ≈ 200 iOS builds/month, sufficient for development.

## Architecture

### CI Pipeline

```yaml
# .github/workflows/mobile.yml — add iOS job
ios-build:
  runs-on: macos-latest  # Blacksmith: use runs-on label per Blacksmith docs
  steps:
    - checkout
    - setup-java@4 (temurin 21)
    - setup-gradle@v4
    - ./gradlew :shared:compileKotlinIosArm64
    - ./gradlew :shared:compileKotlinIosSimulatorArm64
    - ./gradlew :shared:embedAndSignAppleFrameworkForXcode
    - xcodebuild -scheme SkateLab -sdk iphoneos -configuration Debug archive -archivePath build/SkateLab.xcarchive
    - xcodebuild -exportArchive -archivePath build/SkateLab.xcarchive -exportOptionsPlist iosApp/ExportOptions.plist -exportPath build/ipa
    - upload-artifact: build/ipa/*.ipa
```

**Trigger**: `paths: ['mobile/**']`

### Xcode Project Structure

```
iosApp/
├── SkateLab.xcodeproj/
├── SkateLab/
│   ├── App.swift                  # @main entry point
│   ├── ContentView.swift          # ComposeUIViewController host
│   ├── Info.plist                 # Bundle ID, permissions
│   └── Theme/                    # (existing) Swift theme files
└── SkateLibTests/
    └── SkateLabTests.swift
```

**App.swift**:
```swift
import SwiftUI
import shared

@main
struct SkateLabApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
```

**ContentView.swift**:
```swift
import SwiftUI
import shared

struct ContentView: View {
    var body: some View {
        ComposeView().ignoresSafeArea(.all)
    }
}

struct ComposeView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> UIViewController {
        return MainViewControllerKt.MainViewController()
    }
    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}
```

**Bundle ID**: `ru.skatelab.capture`

**KMP-Xcode link**: Gradle `embedAndSignAppleFrameworkForXcode` task generates `shared.xcframework`, Xcode project imports it.

### Local Testing (AltServer-Linux)

```bash
# One-time setup
sudo pacman -S usbmuxd  # Arch/Artix
podman pull ghcr.io/sidestore/altcon

# Install .ipa on device (USB cable connected)
podman run --rm -it \
  -v ${PWD}/:/mnt/ \
  -v /var/run/usbmuxd:/var/run/usbmuxd \
  -v /var/lib/lockdown:/tmp/lockdown \
  ghcr.io/sidestore/altcon
```

**Limitations**: Free Apple ID → 3 apps, 7-day certificate. Refresh by reconnecting USB + re-running altcon.

**Alternative for WiFi refresh** (no WireGuard needed): `sidestore-vpn` on Linux machine in home LAN — swaps packets between iPhone and simulated iTunes. Runs as Docker container on same network.

### TestFlight Distribution (after Apple Developer enrollment)

```yaml
# Add to iOS CI job after .ipa build
- name: Deploy to TestFlight
  if: github.ref == 'refs/heads/master'
  env:
    APP_STORE_CONNECT_ISSUER_ID: ${{ secrets.ASC_ISSUER_ID }}
    APP_STORE_CONNECT_KEY_ID: ${{ secrets.ASC_KEY_ID }}
    APP_STORE_CONNECT_PRIVATE_KEY: ${{ secrets.ASC_PRIVATE_KEY }}
  run: |
    xcrun altool --upload-app \
      --type ios \
      --file build/ipa/SkateLab.ipa \
      --apiKey "$APP_STORE_CONNECT_KEY_ID" \
      --apiIssuer "$APP_STORE_CONNECT_ISSUER_ID"
```

**Secrets needed** (generated in App Store Connect → Users and Access → Integrations → App Store Connect API):
- `ASC_ISSUER_ID`
- `ASC_KEY_ID`
- `ASC_PRIVATE_KEY` (.p8 file content)

## Cost Breakdown

| Phase | When | Cost |
|-------|------|------|
| CI setup (now) | During Android dev | 0 ₽ |
| Xcode project + .ipa in CI | When iOS dev starts | 0 ₽ |
| AltServer-Linux local testing | When iOS dev starts | 0 ₽ |
| Apple Developer Program | When TestFlight/App Store needed | $99/year (~9,900 ₽) |
| App Store publication | When product is ready | $99/year (already paid) |

## Out of Scope

- Compose Multiplatform UI details (separate spec)
- App Store metadata, screenshots, description
- Push notifications, iCloud, other Apple services
- IMU BLE integration on iOS
- Mac Mini purchase (not needed with this approach)

## xtool (Not Used)

[xtool](https://github.com/xtool-org/xtool) (available in AUR) allows building iOS apps on Linux without Xcode. However, it only supports SwiftPM projects — not Kotlin Multiplatform. KMP for iOS compiles through Kotlin/Native which generates a framework linked by Xcode. xtool does not support this pipeline. Not applicable to SkateLab.

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| KMP code breaks iOS target silently | CI catches compilation errors on every push |
| 7-day certificate expiry during dev | AltServer-Linux on USB, refresh weekly. sidestore-vpn for WiFi auto-refresh |
| WireGuard blocked in Russia | Use AltServer USB or sidestore-vpn on LAN (no WireGuard needed) |
| No iOS device for testing | 2 spare iPhones available for sideloading |
| Private repo CI minutes limit | Blacksmith 3,000 free min/month ≈ 200 iOS builds |
| Apple Developer Program delay | 1–2 days for approval. Enroll early when approaching beta |