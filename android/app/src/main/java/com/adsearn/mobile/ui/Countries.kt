package com.adsearn.mobile.ui

import com.google.i18n.phonenumbers.PhoneNumberUtil
import java.util.Locale

data class CountryOption(val iso: String, val name: String, val callingCode: String, val flag: String)

object Countries {
    private val phoneNumbers = PhoneNumberUtil.getInstance()

    val all: List<CountryOption> by lazy {
        Locale.getISOCountries().mapNotNull { iso ->
            val callingCode = phoneNumbers.getCountryCodeForRegion(iso)
            if (callingCode == 0) return@mapNotNull null
            CountryOption(
                iso = iso,
                name = Locale("", iso).getDisplayCountry(Locale.getDefault()),
                callingCode = "+$callingCode",
                flag = iso.uppercase().map { char ->
                    String(Character.toChars(0x1F1E6 + char.code - 'A'.code))
                }.joinToString(""),
            )
        }.sortedBy { it.name }
    }

    fun byIso(iso: String?): CountryOption? = all.firstOrNull { it.iso.equals(iso, ignoreCase = true) }
}
