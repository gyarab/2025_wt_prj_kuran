import { createRouter, createWebHistory } from 'vue-router'
import MovieList    from '../views/MovieList.vue'
import MovieDetail  from '../views/MovieDetail.vue'
import PersonDetail from '../views/PersonDetail.vue'
import LoginView    from '../views/LoginView.vue'
import ProfileView  from '../views/ProfileView.vue'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        { path: '/',                              name: 'home',          component: MovieList   },
        { path: '/movie/:id',                     name: 'movie-detail',  component: MovieDetail },
        { path: '/:type(actor|director|writer)/:id', name: 'person-detail', component: PersonDetail },
        { path: '/login',                         name: 'login',         component: LoginView   },
        { path: '/profile',                       name: 'profile',       component: ProfileView },
    ],
    scrollBehavior: () => ({ top: 0 }),
})

export default router
