# iOS Development Without Mac — Design Spec

> Date: 2026-05-24 (updated)
> Status: Approved (revised after review)
> Approach: Minimal (CI now, iOS dev later)

## Problem

SkateLab mobile app uses Kotlin Multiplatform with Compose Multiplatform. iOS target is declared (`iosArm64`, `iosSimulatorArm64`) but has no Xcode project, no CI, no device testing capability. Team has no macOS hardware. Need a path to build, test, and ship iOS app without Mac.

## Context

- **KMP shared module**: `mobile/shared/` with `commonMain`, `androidMain`, `iosMain`
- **iOS source set**: 1 file — `IosTokenStorage.kt` (Keychain integration)
- **iosApp/**: Only Swift theme files, no Xcode project, no entry point
- **iOS UI approach**: SwiftUI (not shared Compose UI) — per project CLAUDE.md
- **CI**: `mobile.yml` — Android only, no iOS jobs
- **Budget**: $99/year for Apple Developer Program (when needed)
- **Target devices**: iPhone + iPad (Universal)
- **Timeline**: Android first, iOS after stabilization
- **Constraint**: WireGuard blocked in Russia → SideStore VPN not usable over internet

## Architecture Decision: SwiftUI, not shared Compose UI

The shared module is a **data layer** (Ktor, kotlinx-serialization, multiplatform-settings). It does NOT include Compose Multiplatform dependencies. iOS UI will be **SwiftUI** calling shared module APIs.

This means:
- `iosApp/` contains native SwiftUI views
- `shared` module exposes Kotlin APIs via `binaries.framework { baseName = "shared"; isStatic = true }`
- Xcode project links `shared.xcframework` via Gradle `linkDebugFrameworkIosArm64` task
- No `ComposeUIViewController` — no shared UI between Android and iOS

## Implementation Phases

### Phase 1: CI Compile-Only (now, during Android dev)

Add iOS compilation to CI. No Xcode project yet. Catches iOS-specific Kotlin/Native errors on every push.

**Changes required:**

1. Add `binaries.framework` to `shared/build.gradle.kts`:
```kotlin
kotlin {
    iosArm64()
    iosSimulatorArm64()

    binaries.framework {
        baseName = "shared"
        isStatic = true  // required for App Store distribution
    }
}
```

2. Add iOS CI job to `.github/workflows/mobile.yml`:
```yaml
ios-compile:
  runs-on: macos-14  # pin to specific macOS version
  steps:
    - uses: actions/checkout@v4
    - uses: gradle/actions/setup-gradle@v4
      with:
        cache-read-only: ${{ github.ref != 'refs/heads/master' }}
    - name: Set up JDK 17
      uses: actions/setup-java@v4
      with:
        distribution: temurin
        java-version: 17  # match Android build JDK
    - name: Compile iOS frameworks
      working-directory: mobile
      run: |
        ./gradlew :shared:compileKotlinIosArm64
        ./gradlew :shared:compileKotlinIosSimulatorArm64
        ./gradlew :shared:linkDebugFrameworkIosArm64
        ./gradlew :shared:linkReleaseFrameworkIosArm64
    - name: Cache Kotlin/Native compiler
      uses: actions/cache@v4
      with:
        path: ~/.konan
        key: konan-${{ runner.os }}-${{ hashFiles('mobile/gradle/libs.versions.toml') }}
```

**Trigger**: `paths: ['mobile/**']`

### Phase 2: Xcode Project + .ipa Build (when iOS dev starts)

Create Xcode project in `iosApp/` that links the KMP framework.

**Xcode project structure:**
```
iosApp/
├── SkateLab.xcodeproj/
├── SkateLab/
│   ├── App.swift                  # @main entry point
│   ├── ContentView.swift          # SwiftUI root view
│   ├── Info.plist                 # Bundle ID, permissions
│   └── Theme/                    # (existing) Swift theme files
└── SkateLabTests/
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
        Text("SkateLab iOS")
            .font(.title)
            .padding()
    }
}

#Preview {
    ContentView()
}
```

**Bundle ID**: `ru.skatelab.capture`

**Xcode-KMP link**: Xcode project has a "Run Script" build phase:
```bash
cd "$SRCROOT/.." && ./gradlew :shared:linkDebugFrameworkIosArm64
```
Then links `shared.framework` in "Frameworks, Libraries, and Embedded Content".

**CI .ipa build** (added to iOS job):
```yaml
    - name: Build .ipa
      working-directory: mobile
      run: |
        xcodebuild -scheme SkateLab \
          -sdk iphoneos \
          -configuration Debug \
          -archivePath build/SkateLab.xcarchive \
          archive
        xcodebuild -exportArchive \
          -archivePath build/SkateLab.xcarchive \
          -exportOptionsPlist iosApp/ExportOptions.plist \
          -exportPath build/ipa
    - name: Upload .ipa artifact
      uses: actions/upload-artifact@v4
      with:
        name: SkateLab.ipa
        path: mobile/build/ipa/*.ipa
```

**ExportOptions.plist** (must be created):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>development</string>
    <key>teamID</key>
    <string>TEAM_ID_PLACEHOLDER</string>
    <key>provisioningProfiles</key>
    <dict>
        <key>ru.skatelab.capture</key>
        <string>SkateLab_Development</string>
    </dict>
</dict>
</plist>
```

### Phase 3: Local Testing (AltServer-Linux)

When you have an `.ipa` and want to test on a real device.

```bash
# One-time setup
sudo pacman -S usbmuxd  # Arch/Artix
podman pull ghcr.io/sidestore/altcon

# Install .ipa on device (USB cable connected)
podman run --rm -it \
  --network host \
  -v ${PWD}/:/mnt/ \
  -v /var/run/usbmuxd:/var/run/usbmuxd \
  -v /var/lib/lockdown:/tmp/lockdown \
  ghcr.io/sidestore/altcon
```

**Note**: `--network host` is required — altcon needs internet access to contact Apple servers for certificate signing.

**Limitations**: Free Apple ID → 3 apps, 7-day certificate. Refresh by reconnecting USB + re-running altcon.

**Alternative for WiFi refresh on home LAN** (no WireGuard needed): `sidestore-vpn` runs a local Anisette server on your Linux machine. It intercepts traffic from iPhone to `10.7.0.1` on your local network. iPhone must be on the same WiFi. This is LAN-only, does NOT use WireGuard tunneling over the internet.

### Phase 4: TestFlight Distribution (after Apple Developer enrollment)

When Apple Developer Program is purchased ($99/year):

```yaml
# Add to iOS CI job after .ipa build
- name: Write API key
  run: mkdir -p ~/private_keys && echo "$ASC_PRIVATE_KEY" > ~/private_keys/AuthKey_${{ secrets.ASC_KEY_ID }}.p8

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
- `ASC_PRIVATE_KEY` (.p8 file content — must be written to `~/private_keys/AuthKey_<KEY_ID>.p8` before altool call)

## Cost Breakdown

| Phase | When | Cost |
|-------|------|------|
| Phase 1: CI compile-only (now) | During Android dev | 0 ₽ (Blacksmith 3,000 free min) |
| Phase 2: Xcode project + .ipa | When iOS dev starts | 0 ₽ |
| Phase 3: AltServer-Linux | When iOS dev starts | 0 ₽ |
| Phase 4: Apple Developer Program | When TestFlight/App Store needed | $99/year (~9,900 ₽) |
| App Store publication | When product is ready | $99/year (already paid) |

**Private repo CI cost without Blacksmith**: GitHub Actions macOS runners consume minutes at ×10 multiplier. One iOS build ≈ 15 min real time = 150 billed min. Free plan = 2,000 min/month = ~13 builds/month.

## Out of Scope

- Compose Multiplatform shared UI for iOS (separate decision, not this spec)
- App Store metadata, screenshots, description
- Push notifications, iCloud, other Apple services
- IMU BLE integration on iOS
- Mac Mini purchase (not needed with this approach)
- `iosX64()` target (Intel Mac simulators not supported — Apple Silicon simulators only)

## xtool (Not Used)

[xtool](https://github.com/xtool-org/xtool) (available in AUR) allows building iOS apps on Linux without Xcode. However, it only supports SwiftPM projects — not Kotlin Multiplatform. KMP for iOS compiles through Kotlin/Native which generates a framework that must be linked by Xcode. xtool does not support this pipeline. Not applicable to SkateLab.

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| KMP code breaks iOS target silently | Phase 1 CI catches compilation errors on every push |
| 7-day certificate expiry during dev | AltServer-Linux on USB, refresh weekly. sidestore-vpn on LAN for auto-refresh |
| WireGuard blocked in Russia | Use AltServer USB or sidestore-vpn on LAN (local network only, no WireGuard over internet) |
| No iOS device for testing | 2 spare iPhones available for sideloading |
| Private repo CI minutes limit | Blacksmith 3,000 free min/month ≈ 200 iOS builds. Fallback: make repo public for unlimited minutes |
| Apple Developer Program delay | 1–2 days for approval. Enroll early when approaching beta |
| Xcode project creation requires macOS | Create on CI runner or use `xcodegen` tool that generates .xcodeproj from YAML spec |
| `ExportOptions.plist` needs Team ID | Placeholder until Apple Developer enrollment; CI generates .ipa with `method: development` for sideloading |