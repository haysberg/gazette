package main

import (
	"log"

	"github.com/cavaliercoder/grab"
	"gorm.io/gorm"
)

type FeedList struct {
	Feeds []Feed `toml:"feedlist"`
}

type Feed struct {
	gorm.Model
	Link     string  `gorm:"primaryKey" toml:"link"`
	Domain   *string `toml:"domain"`
	Title    *string `toml:"title"`
	Subtitle *string `toml:"subtitle"`
	Image    *string `toml:"image"`
	Posts    []Post  `gorm:"foreignKey:Link"`
}

func NewFeed()

func (feed Feed) DownloadFeedIcon() {
	resp, err := grab.Get(".", "http://www.golang-book.com/public/pdf/gobook.pdf")
	if err != nil {
		log.Fatal(err)
	}
}
