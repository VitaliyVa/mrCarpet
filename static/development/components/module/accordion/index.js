import "./index.scss"

document.querySelectorAll('.accordion__title').forEach(item => {
    item.addEventListener('click', () => {
        item.closest('.accordion_content__block').classList.toggle('active')
    })
})
