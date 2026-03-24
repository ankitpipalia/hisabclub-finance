package com.hisabclub.app.smsreader

import android.Manifest
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.provider.Telephony
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.*
import com.facebook.react.module.annotations.ReactModule

/**
 * Native module to read SMS inbox on Android.
 * Queries content://sms/inbox and returns structured SMS data.
 *
 * Methods exposed to JS:
 * - readInbox(sinceTimestamp: Double) -> Promise<Array<{id, address, body, date}>>
 * - hasPermission() -> Promise<Boolean>
 * - requestPermission() -> Promise<Boolean>
 */
@ReactModule(name = SmsReaderModule.NAME)
class SmsReaderModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    companion object {
        const val NAME = "SmsReaderModule"
    }

    override fun getName(): String = NAME

    @ReactMethod
    fun hasPermission(promise: Promise) {
        val granted = ContextCompat.checkSelfPermission(
            reactApplicationContext,
            Manifest.permission.READ_SMS
        ) == PackageManager.PERMISSION_GRANTED
        promise.resolve(granted)
    }

    @ReactMethod
    fun requestPermission(promise: Promise) {
        // Permission must be requested via the Activity (PermissionsAndroid in JS)
        // This just checks current state
        val granted = ContextCompat.checkSelfPermission(
            reactApplicationContext,
            Manifest.permission.READ_SMS
        ) == PackageManager.PERMISSION_GRANTED
        promise.resolve(granted)
    }

    @ReactMethod
    fun readInbox(sinceTimestamp: Double, promise: Promise) {
        try {
            val permission = ContextCompat.checkSelfPermission(
                reactApplicationContext,
                Manifest.permission.READ_SMS
            )
            if (permission != PackageManager.PERMISSION_GRANTED) {
                promise.reject("PERMISSION_DENIED", "READ_SMS permission not granted")
                return
            }

            val messages = WritableNativeArray()
            val uri = Uri.parse("content://sms/inbox")
            val projection = arrayOf("_id", "address", "body", "date")
            val selection = "date > ?"
            val selectionArgs = arrayOf(sinceTimestamp.toLong().toString())
            val sortOrder = "date DESC"

            val cursor: Cursor? = reactApplicationContext.contentResolver.query(
                uri, projection, selection, selectionArgs, sortOrder
            )

            cursor?.use {
                val idIdx = it.getColumnIndex("_id")
                val addressIdx = it.getColumnIndex("address")
                val bodyIdx = it.getColumnIndex("body")
                val dateIdx = it.getColumnIndex("date")

                while (it.moveToNext()) {
                    val sms = WritableNativeMap()
                    sms.putString("id", it.getString(idIdx))
                    sms.putString("address", it.getString(addressIdx) ?: "")
                    sms.putString("body", it.getString(bodyIdx) ?: "")
                    sms.putDouble("date", it.getLong(dateIdx).toDouble())
                    messages.pushMap(sms)
                }
            }

            promise.resolve(messages)
        } catch (e: Exception) {
            promise.reject("SMS_READ_ERROR", e.message, e)
        }
    }
}
