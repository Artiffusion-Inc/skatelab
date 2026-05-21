package ru.skatelab.capture.data.share

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ShareManager
    @Inject
    constructor(
        @ApplicationContext private val context: Context,
    ) {
        fun getShareUri(file: File): Uri =
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file,
            )
    }
