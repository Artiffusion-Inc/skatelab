# ============================================================
# SkateLab ProGuard Rules — R8 Full Mode
# Strategy: Minimize manual rules. Prefer library consumer rules.
# ============================================================

# === kotlinx.serialization ===
# Consumer rules bundled since v1.7+. Explicit safety net:
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    static ** Companion;
}
-if @kotlinx.serialization.Serializable class ** {
    static **$* *;
}
-keepclassmembers class <2>$<3> {
    kotlinx.serialization.KSerializer serializer(...);
}
-if @kotlinx.serialization.Serializable class ** {
    public static ** INSTANCE;
}
-keepclassmembers class <1> {
    public static <1> INSTANCE;
    kotlinx.serialization.KSerializer serializer(...);
}
-keepclassmembers public class **$$serializer {
    private ** descriptor;
}
-keepattributes RuntimeVisibleAnnotations, AnnotationDefault
-dontnote kotlinx.serialization.**
-dontwarn kotlinx.serialization.internal.ClassValueReferences

# === Ktor Client ===
# No consumer rules. Narrow keeps only — do NOT use -keep class io.ktor.**
-keep class io.ktor.client.plugins.** { *; }
-dontwarn io.ktor.**

# === OkHttp (consumer rules bundled, safety net) ===
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# === Room (consumer rules bundled, safety net) ===
-keep class * extends androidx.room.RoomDatabase { *; }

# === Hilt / Dagger (consumer rules bundled, safety net) ===
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }

# === Kable BLE (no consumer rules) ===
-keep class com.juul.kable.** { public *; }
-dontwarn com.juul.kable.**

# === SkateLab models (serialized) ===
-keep class ru.skatelab.shared.models.** { *; }
-keep class ru.skatelab.shared.api.** { *; }
-keep class ru.skatelab.shared.auth.** { *; }

# === Protobuf (existing) ===
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    *** dynamicMethod(com.google.protobuf.GeneratedMessageLite$MethodToInvoke, java.lang.Object, java.lang.Object);
}
-keep class ru.skatelab.capture.proto.** { *; }

# === Kotlin coroutines (consumer rules bundled, safety net) ===
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.coroutines.** {
    volatile <fields>;
}

# === General Android ===
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# === R8 diagnostics (CI review) ===
-printconfiguration build/outputs/mapping/release-configuration.txt
-printseeds build/outputs/mapping/release-seeds.txt
-printusage build/outputs/mapping/release-usage.txt
