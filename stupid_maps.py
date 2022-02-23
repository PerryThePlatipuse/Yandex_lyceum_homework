import pygame
import requests
import sys
import os
import math

from PRIVATE_KEY import private_key, maps_key

DELTA_LAT = 0.002
DELTA_LON = 0.002
coord_to_geo_x = 0.0000428  # proportions
coord_to_geo_y = 0.0000428


# Найти объект по координатам.
def response_from_api(mouse_pos):
    url = f"http://geocode-maps.yandex.ru/1.x/?apikey={maps_key}&geocode={mouse_pos}&format=json"
    request = url.format(**locals())
    response = requests.get(request)
    if not response:
        raise RuntimeError(
            f"""Ошибка выполнения запроса: {request}
            HTTP status {response.status_code} ({response.reason})""")
    json_response = response.json()
    # Получаем первый топоним из ответа геокодера.
    sp = json_response["response"]["GeoObjectCollection"]["featureMember"]
    return sp[0]["GeoObject"] if sp else None


def organisations(ll):
    url = "https://search-maps.yandex.ru/v1/"
    params = {"apikey": private_key, "lang": "ru_RU", "ll": ll, "spn": "0.001,0.001", "type": "biz", "text": ll}
    response = requests.get(url, params=params)
    if not response:
        raise RuntimeError(
            f"""Ошибка выполнения запроса: {url}
            HTTP status {response.status_code} ({response.reason})""")
    # Преобразуем ответ в json-объект
    json_response = response.json()

    # Получаем первую найденную организацию.
    sp = json_response["features"]
    return sp[0] if sp else None


def lonlat_distance(a, b):
    degree_to_meters_factor = 111 * 1000  # 111 километров в метрах
    a_lon, a_lat = a
    b_lon, b_lat = b

    # Берем среднюю по широте точку и считаем коэффициент для нее.
    radians_lattitude = math.radians((a_lat + b_lat) / 2.)
    lat_lon_factor = math.cos(radians_lattitude)

    # Вычисляем смещения в метрах по вертикали и горизонтали.
    dx = abs(a_lon - b_lon) * degree_to_meters_factor * lat_lon_factor
    dy = abs(a_lat - b_lat) * degree_to_meters_factor

    # Вычисляем расстояние между точками.
    distance = math.sqrt(dx * dx + dy * dy)

    return distance


def ll(x, y):
    return f"{x},{y}"


# Структура для хранения результатов поиска:
# координаты объекта, его название и почтовый индекс, если есть.

class SearchResult(object):
    def __init__(self, point, address, postal_code=None):
        self.point = point
        self.address = address
        self.postal_code = postal_code


# Параметры отображения карты:
# координаты, масштаб, найденные объекты и т.д.

class MapParams(object):
    # Параметры по умолчанию.
    def __init__(self):
        self.lat = 55.753933
        self.lon = 37.620735
        self.zoom = 15
        self.type = "map"
        self.search_result = None
        self.use_postal_code = False

    # Преобразование координат в параметр ll
    def ll(self):
        return f"{self.lon},{self.lat}"

    # Обновление параметров карты по нажатой клавише.
    def update(self, event):
        if event.key == pygame.K_PAGEUP and self.zoom < 19:
            self.zoom += 1
        elif event.key == pygame.K_PAGEDOWN and self.zoom > 2:
            self.zoom -= 1
        elif event.key == pygame.K_LEFT:
            self.lon -= DELTA_LON * math.pow(2, 15 - self.zoom)
        elif event.key == pygame.K_RIGHT:
            self.lon += DELTA_LON * math.pow(2, 15 - self.zoom)
        elif event.key == pygame.K_UP and self.lat < 85:
            self.lat += DELTA_LAT * math.pow(2, 15 - self.zoom)
        elif event.key == pygame.K_DOWN and self.lat > -85:
            self.lat -= DELTA_LAT * math.pow(2, 15 - self.zoom)
        elif event.key == pygame.K_1:
            self.type = "map"
        elif event.key == pygame.K_2:
            self.type = "sat"
        elif event.key == pygame.K_3:
            self.type = "sat,skl"
        elif event.key == pygame.K_DELETE:
            self.search_result = None
        elif event.key == pygame.K_F10:
            self.use_postal_code = not self.use_postal_code
        if self.lon > 180: self.lon -= 360
        if self.lon < -180: self.lon += 360

    # Преобразование экранных координат в географические.
    def screen_to_geo(self, pos):
        dy = 225 - pos[1]
        dx = pos[0] - 300
        lx = self.lon + dx * coord_to_geo_x * math.pow(2, 15 - self.zoom)
        ly = self.lat + dy * coord_to_geo_y * math.cos(math.radians(self.lat)) * math.pow(2,
                                                                                          15 - self.zoom)
        return lx, ly

    # Добавить результат геопоиска на карту.
    def address_from_api(self, pos):
        point = self.screen_to_geo(pos)
        toponym = response_from_api(ll(point[0], point[1]))
        self.search_result = SearchResult(
            point,
            toponym["metaDataProperty"]["GeocoderMetaData"]["text"] if toponym else None,
            toponym["metaDataProperty"]["GeocoderMetaData"]["Address"].get(
                "postal_code") if toponym else None)

    # Добавить результат поиска организации на карту.
    def add_reverse_org_search(self, pos):
        self.search_result = None
        point = self.screen_to_geo(pos)
        org = organisations(ll(point[0], point[1]))
        if not org:
            return

        org_point = org["geometry"]["coordinates"]
        org_lon = float(org_point[0])
        org_lat = float(org_point[1])

        # Проверяем, что найденный объект не дальше 50м от места клика.
        if lonlat_distance((org_lon, org_lat), point) <= 50:
            self.search_result = SearchResult(point, org["properties"]["CompanyMetaData"]["name"])


def load_map(mp):
    map_request = "http://static-maps.yandex.ru/1.x/?ll={ll}&z={z}&l={type}".format(ll=mp.ll(),
                                                                                    z=mp.zoom,
                                                                                    type=mp.type)
    if mp.search_result:
        map_request += "&pt={0},{1},pm2grm".format(mp.search_result.point[0],
                                                   mp.search_result.point[1])

    response = requests.get(map_request)
    if not response:
        print("Ошибка выполнения запроса:")
        print(map_request)
        print("Http статус:", response.status_code, "(", response.reason, ")")
        sys.exit(1)
    map_file = "map.png"
    try:
        with open(map_file, "wb") as file:
            file.write(response.content)
    except IOError as ex:
        print("Ошибка записи временного файла:", ex)
        sys.exit(2)

    return map_file


def render_text(text):
    font = pygame.font.Font(None, 30)
    return font.render(text, 1, (100, 0, 100))


def main():
    pygame.init()
    screen = pygame.display.set_mode((600, 450))
    mp = MapParams()

    while True:
        event = pygame.event.wait()
        if event.type == pygame.QUIT:
            break
        elif event.type == pygame.KEYUP:
            mp.update(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                mp.address_from_api(event.pos)
            elif event.button == 3:
                mp.add_reverse_org_search(event.pos)
        else:
            continue

        map_file = load_map(mp)

        screen.blit(pygame.image.load(map_file), (0, 0))

        if mp.search_result:
            if mp.use_postal_code and mp.search_result.postal_code:
                text = render_text(mp.search_result.postal_code + ", " + mp.search_result.address)
            else:
                text = render_text(mp.search_result.address)
            screen.blit(text, (20, 400))

        pygame.display.flip()

    pygame.quit()
    os.remove(map_file)


if __name__ == "__main__":
    main()
