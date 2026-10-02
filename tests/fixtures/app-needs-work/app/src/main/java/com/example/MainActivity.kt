package com.example

import android.app.Activity
import android.net.nsd.NsdManager
import android.view.KeyEvent

class MainActivity : Activity() {
    override fun onBackPressed() {
        super.onBackPressed()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK) return true
        return super.onKeyDown(keyCode, event)
    }

    fun discover() {
        val nsd = getSystemService(NsdManager::class.java)
        // service discovery on the LAN
    }
}
