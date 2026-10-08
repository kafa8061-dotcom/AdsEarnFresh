package com.adsearn.mobile.ui

import com.google.i18n.phonenumbers.PhoneNumberUtil
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CountryDirectoryTest {
    @Test
    fun countrySelectionDerivesExpectedCallingCodes() {
        assertEquals("+254", Countries.byIso("KE")?.callingCode)
        assertEquals("+252", Countries.byIso("SO")?.callingCode)
        assertEquals("+1", Countries.byIso("US")?.callingCode)
        assertEquals("+44", Countries.byIso("GB")?.callingCode)
    }

    @Test
    fun searchableDirectoryProvidesCountryNamesAndFlags() {
        val kenya = Countries.all.first { it.iso == "KE" }
        assertEquals("Kenya", kenya.name)
        assertTrue(kenya.flag.isNotBlank())
        assertTrue(Countries.all.size > 200)
    }

    @Test
    fun supportedNationalPhoneNumbersPassInternationalValidation() {
        val util = PhoneNumberUtil.getInstance()
        assertTrue(util.isValidNumberForRegion(util.parse("712345678", "KE"), "KE"))
        assertTrue(util.isValidNumberForRegion(util.parse("612345678", "SO"), "SO"))
    }
}
