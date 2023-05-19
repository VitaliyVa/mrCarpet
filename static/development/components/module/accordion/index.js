import "./index.scss"

document.querySelectorAll('.accordion_content__block').forEach(item => {
    item.addEventListener('click', () => {
        item.classList.toggle('active')
    })
})