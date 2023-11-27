/*!
 * Color mode toggler for Bootstrap's
 * Copyright 2011-2023 Swasher
 * Licensed under the Creative Commons Attribution 3.0 Unported License.
 */

(() => {
    'use strict'

    const storedTheme = localStorage.getItem('theme')

    const getPreferredTheme = () => {
        if (storedTheme) {
            // console.log('getPreferredTheme from STORED', storedTheme)
            return storedTheme
        }
        // console.log('getPreferredTheme from SYSTEM', window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }

    const setTheme = function (theme) {
      if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-bs-theme', 'dark')
      } else {
        document.documentElement.setAttribute('data-bs-theme', theme)
      }
    }

    const setToggler = (theme) => {
        // console.log('Set toggler ->', theme)

        let toggler = document.getElementById('theme-toggler')
        toggler.setAttribute('data-bs-theme-value', theme)
        if (theme === 'light') {
            // console.log('Set icon -> light')
            toggler.querySelector('i').setAttribute('class','bi bi-lightbulb-fill');
            // toggler.querySelector('i').setAttribute('class','bi bi-sun-fill');
        } else {
            // console.log('Set icon -> dark')
            // toggler.querySelector('i').className('bi bi-lightning-charge-fill');
            toggler.querySelector('i').setAttribute('class','bi bi-moon-stars-fill  ');
            // toggler.querySelector('i').setAttribute('class','bi bi-lightbulb-off');
        }
    }


    setTheme(getPreferredTheme())
    setToggler(getPreferredTheme())


    window.addEventListener('DOMContentLoaded', () => {
        // showActiveTheme(getPreferredTheme())

        let toggler = document.querySelector('[data-bs-theme-value]')

        toggler.addEventListener('click', () => {
            const current_theme = toggler.getAttribute('data-bs-theme-value')
            // console.log('Read theme from toggler:', current_theme)

            let theme = current_theme==='light' ? 'dark' : 'light'
            localStorage.setItem('theme', theme)
            setTheme(theme)
            setToggler(theme)
        })
    })
})()
