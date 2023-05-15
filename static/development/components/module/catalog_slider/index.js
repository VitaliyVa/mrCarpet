import './index.scss';
import Swiper, {
    Navigation,
} from 'swiper';
import 'swiper/swiper-bundle.css'
import './index.scss'

Swiper.use([Navigation])

const catalog_slider = new Swiper(".catalog-swiper", {
    slidesPerView: '4',
    spaceBetween: 30,

    navigation: {
        nextEl: ".swiper-button-next",
        prevEl: ".swiper-button-prev",
    },
})

